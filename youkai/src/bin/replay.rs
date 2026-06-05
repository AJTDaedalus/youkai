use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use anyhow::{Context, Result};
use clap::Parser;

/// KCP Segment Header structure
#[derive(Debug, Clone)]
pub struct KcpHeader {
    pub conv: u32,
    pub cmd: u8,
    pub frg: u8,
    pub wnd: u16,
    pub ts: u32,
    pub sn: u32,
    pub una: u32,
    pub len: u32,
}

impl KcpHeader {
    /// Attempts to parse a shuffled KCP header from 24 bytes (ZZZ format)
    pub fn parse(bytes: &[u8]) -> Option<Self> {
        if bytes.len() < 24 {
            return None;
        }
        Some(Self {
            conv: u32::from_le_bytes(bytes[0..4].try_into().unwrap()),
            // ZZZ Shuffled Layout:
            ts: u32::from_le_bytes(bytes[4..8].try_into().unwrap()),
            cmd: bytes[8],
            frg: bytes[9],
            wnd: u16::from_le_bytes(bytes[10..12].try_into().unwrap()),
            sn: u32::from_le_bytes(bytes[12..16].try_into().unwrap()),
            una: u32::from_le_bytes(bytes[16..20].try_into().unwrap()),
            len: u32::from_le_bytes(bytes[20..24].try_into().unwrap()),
        })
    }
}

/// Connection Handshake structure representing the initial login exchange
#[derive(Debug, Clone)]
pub struct HandshakePacket {
    pub conv: u32,
    pub magic: u32,
    pub seed: u32,
}

impl HandshakePacket {
    /// Attempts to parse a connection handshake packet from raw UDP bytes
    pub fn parse(bytes: &[u8]) -> Option<Self> {
        if bytes.len() < 32 {
            return None;
        }
        let conv = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
        let magic = u32::from_le_bytes(bytes[24..28].try_into().unwrap());
        
        // standard handshake connect magic (0x00000010 / 0x10000000)
        if magic == 0x00000010 || magic == 0x10000000 {
            let seed = u32::from_le_bytes(bytes[28..32].try_into().unwrap());
            return Some(Self { conv, magic, seed });
        }
        None
    }
}

#[derive(Parser, Debug)]
#[command(author, version, about = "Offline packet diagnostic and replay tool")]
struct Args {
    /// Path to the folder containing raw packet `.bin` dumps
    #[arg(short = 'd', long, default_value = "/mnt/c/Users/laharre/AppData/Roaming/youkai/data/packet_log")]
    log_dir: String,

    /// Limit the number of packets to process
    #[arg(short = 'n', long)]
    limit: Option<usize>,

    /// Show detailed verbose output for every packet
    #[arg(short = 'v', long, default_value_t = false)]
    verbose: bool,

    /// Optional hex-encoded XOR key to simulate stream decryption
    #[arg(short = 'x', long)]
    xor_key: Option<String>,
}

fn hex_to_bytes(hex: &str) -> Option<Vec<u8>> {
    let cleaned: String = hex.chars().filter(|c| c.is_ascii_hexdigit()).collect();
    if cleaned.len() % 2 != 0 {
        return None;
    }
    (0..cleaned.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&cleaned[i..i + 2], 16).ok())
        .collect()
}

fn main() -> Result<()> {
    let args = Args::parse();
    let path = Path::new(&args.log_dir);

    println!("====================================================");
    println!("          Youkai Offline Packet Diagnostic          ");
    println!("====================================================");
    println!("Scanning directory: {:?}", path);

    if !path.exists() {
        println!("Error: Path does not exist!");
        println!("Please check that the Youkai application has logged packets and that the WSL mount path is correct.");
        return Ok(());
    }

    // Parse simulated XOR key if provided
    let mut key_bytes = None;
    if let Some(ref hex_key) = args.xor_key {
        if let Some(parsed_key) = hex_to_bytes(hex_key) {
            println!("Loaded simulated stream decryption key ({} bytes)", parsed_key.len());
            key_bytes = Some(parsed_key);
        } else {
            println!("Warning: Invalid hex format for XOR key. Proceeding without key.");
        }
    }

    // Read and sort files by filename to ensure chronological processing
    let mut entries: Vec<PathBuf> = fs::read_dir(path)?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .filter(|path| path.extension().map_or(false, |ext| ext == "bin"))
        .collect();

    entries.sort_by(|a, b| a.file_name().cmp(&b.file_name()));
    let total_logs = entries.len();
    println!("Found {} raw packet log files.", total_logs);

    let mut processed = 0;
    let mut total_udp_payload_bytes = 0;
    let mut session_counts: BTreeMap<u32, usize> = BTreeMap::new();
    let mut size_distribution: BTreeMap<usize, usize> = BTreeMap::new();
    let mut parse_success_count = 0;
    let mut handshake_count = 0;

    println!("\nAnalyzing packet stream structures (first {} packets)...", args.limit.unwrap_or(total_logs));
    if args.verbose {
        println!("\nID    | Timestamp / Filename                | Size | Potential Session | Raw Hex Payload (First 16 bytes)");
        println!("------|-------------------------------------|------|-------------------|---------------------------------");
    }

    for (index, entry) in entries.iter().enumerate() {
        if let Some(l) = args.limit {
            if processed >= l {
                break;
            }
        }

        let file_bytes = fs::read(entry)
            .with_context(|| format!("Failed to read file: {:?}", entry))?;

        // Extract Layer-4 UDP payload from Layer-2 Ethernet Frame
        let mut udp_payload = file_bytes.clone();
        if file_bytes.len() >= 42 && file_bytes[12] == 0x08 && file_bytes[13] == 0x00 {
            let ip_header_len = ((file_bytes[14] & 0x0F) * 4) as usize;
            let ip_proto = file_bytes[23];
            if ip_proto == 17 && file_bytes.len() >= 14 + ip_header_len + 8 {
                let payload_offset = 14 + ip_header_len + 8;
                if file_bytes.len() >= payload_offset {
                    udp_payload = file_bytes[payload_offset..].to_vec();
                }
            }
        }

        let udp_len = udp_payload.len();
        total_udp_payload_bytes += udp_len;
        *size_distribution.entry(udp_len).or_insert(0) += 1;

        // Apply simulated decryption if enabled
        if let Some(ref key) = key_bytes {
            for (i, byte) in udp_payload.iter_mut().enumerate() {
                *byte ^= key[i % key.len()];
            }
        }

        // Check for connection handshake first
        let mut handshake_detected = false;
        let mut handshake_seed = 0u32;
        if let Some(handshake) = HandshakePacket::parse(&udp_payload) {
            handshake_detected = true;
            handshake_seed = handshake.seed;
            handshake_count += 1;
        }

        // Parse potential session ID (first 4 bytes of UDP payload)
        let mut session_id = 0u32;
        if udp_len >= 4 {
            session_id = u32::from_le_bytes(udp_payload[0..4].try_into().unwrap());
            *session_counts.entry(session_id).or_insert(0) += 1;
        }

        // Attempt KCP parsing
        let mut kcp_parsed = false;
        if udp_len >= 24 && !handshake_detected {
            if let Some(header) = KcpHeader::parse(&udp_payload) {
                // If it looks like a valid KCP command (81, 82, 83, 84) and fits length constraints
                if (header.cmd == 81 || header.cmd == 82 || header.cmd == 83 || header.cmd == 84) 
                   && (header.len as usize + 24 <= udp_len) {
                    kcp_parsed = true;
                    parse_success_count += 1;
                }
            }
        }

        if args.verbose {
            let file_name = entry.file_name().unwrap_or_default().to_string_lossy();
            let truncated_name = if file_name.len() > 30 { &file_name[0..30] } else { &file_name };
            
            let hex_dump = udp_payload.iter()
                .take(16)
                .map(|b| format!("{:02X}", b))
                .collect::<Vec<String>>()
                .join("-");

            let parsed_marker = if handshake_detected {
                format!(" [HS] (seed: 0x{:08X})", handshake_seed)
            } else if kcp_parsed {
                " [KCP]".to_string()
            } else {
                "".to_string()
            };

            println!(
                "{:5} | {:35} | {:4} | 0x{:08X}{} | {}",
                index,
                truncated_name,
                udp_len,
                session_id,
                parsed_marker,
                hex_dump
            );
        }

        processed += 1;
    }

    println!("\n====================================================");
    println!("                  Summary Report                    ");
    println!("====================================================");
    println!("Total log files processed:      {}", processed);
    println!("Total UDP payload bytes:        {} bytes", total_udp_payload_bytes);
    println!("Successfully parsed KCP blocks: {}", parse_success_count);
    println!("Connection handshakes parsed:   {}", handshake_count);
    
    println!("\nUnique Session/Conversation IDs (Top 5):");
    let mut sorted_sessions: Vec<(&u32, &usize)> = session_counts.iter().collect();
    sorted_sessions.sort_by(|a, b| b.1.cmp(a.1));
    for (sess_id, count) in sorted_sessions.iter().take(5) {
        println!("  - ID 0x{:08X} (Session token / KCP conv): {} packets", sess_id, count);
    }

    println!("\nPayload Size Distribution:");
    for (size, count) in size_distribution.iter().take(10) {
        println!("  - {} bytes: {} packets", size, count);
    }
    if size_distribution.len() > 10 {
        println!("  - ... and {} other size categories.", size_distribution.len() - 10);
    }
    println!("====================================================");

    Ok(())
}
