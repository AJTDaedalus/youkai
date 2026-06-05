use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::Path;
use anyhow::Result;
use rand_mt::{Mt, Mt64};

const DEFAULT_LOG_DIR: &str = "/mnt/c/Users/laharre/AppData/Roaming/youkai/data/packet_log";
const TARGET_CONV: u32 = 0x0032_F714;
// Seed bytes at offset [8..12] of the 20-byte ZZZ SYN-ACK for session 0x0032F714
// SYN-ACK raw: 00000145 0032F714 CDD99C5F 499602D2 14514545
// bytes[8..12] = CD D9 9C 5F → LE u32 = 0x5F9CD9CD
const TOKEN_BYTES: [u8; 4] = [0xCD, 0xD9, 0x9C, 0x5F];
const MIHOY_MAGIC: [u8; 4] = [0x01, 0x23, 0x45, 0x67];

/// Strip Ethernet/IP/UDP framing. Returns the UDP payload, or None if not IPv4/UDP.
fn strip_ethernet(file_bytes: &[u8]) -> Option<Vec<u8>> {
    if file_bytes.len() < 42 { return None; }
    // EtherType 0x0800 = IPv4
    if file_bytes[12] != 0x08 || file_bytes[13] != 0x00 { return None; }
    let ip_header_len = ((file_bytes[14] & 0x0F) * 4) as usize;
    // IP protocol 17 = UDP
    if file_bytes[23] != 17 { return None; }
    let udp_start = 14 + ip_header_len;
    if file_bytes.len() < udp_start + 8 { return None; }
    let payload_start = udp_start + 8;
    if file_bytes.len() <= payload_start { return None; }
    Some(file_bytes[payload_start..].to_vec())
}

#[derive(Debug)]
struct KcpSegment {
    sn: u32,
    frg: u8,
    data: Vec<u8>,
}

// ZZZ KCP header is 28 bytes:
//   conv(4) ts(4) cmd(1) frg(1) wnd(2) sn(4) una(4) ???(4) len(4)
// Multiple segments can be packed into a single UDP payload.
const KCP_HDR: usize = 28;

/// Parse all cmd=81 KCP segments from a UDP payload.
/// ZZZ packs multiple KCP segments into one UDP datagram.
fn parse_kcp_data_segments(bytes: &[u8]) -> Vec<KcpSegment> {
    let mut out = Vec::new();
    let mut offset = 0;
    while offset + KCP_HDR <= bytes.len() {
        let h = &bytes[offset..];
        let cmd = h[8];
        let frg = h[9];
        let sn = u32::from_le_bytes(h[12..16].try_into().unwrap());
        let len = u32::from_le_bytes(h[24..28].try_into().unwrap()) as usize;
        let data_end = offset + KCP_HDR + len;
        if data_end > bytes.len() { break; }
        if cmd == 81 {
            out.push(KcpSegment {
                sn,
                frg,
                data: bytes[offset + KCP_HDR..data_end].to_vec(),
            });
        }
        offset = data_end;
        if len == 0 { break; } // guard against infinite loop on zero-len non-data segment
    }
    out
}

fn keystream_mt64(seed: u64, extract_le: bool, count: usize) -> Vec<u8> {
    let mut mt = Mt64::new(seed);
    let mut out = Vec::with_capacity(count + 8);
    while out.len() < count {
        let val = mt.next_u64();
        let bytes = if extract_le { val.to_le_bytes() } else { val.to_be_bytes() };
        out.extend_from_slice(&bytes);
    }
    out.truncate(count);
    out
}

fn rc4_keystream(key: &[u8], count: usize) -> Vec<u8> {
    let mut s = [0u8; 256];
    for i in 0..256 { s[i] = i as u8; }
    let mut j: usize = 0;
    for i in 0..256 {
        j = (j + s[i] as usize + key[i % key.len()] as usize) % 256;
        s.swap(i, j);
    }
    let mut out = Vec::with_capacity(count);
    let (mut ii, mut jj) = (0usize, 0usize);
    for _ in 0..count {
        ii = (ii + 1) % 256;
        jj = (jj + s[ii] as usize) % 256;
        s.swap(ii, jj);
        let t = (s[ii] as usize + s[jj] as usize) % 256;
        out.push(s[t]);
    }
    out
}

fn keystream_mt32(seed: u32, extract_le: bool, count: usize) -> Vec<u8> {
    let mut mt = Mt::new(seed);
    let mut out = Vec::with_capacity(count + 4);
    while out.len() < count {
        let val = mt.next_u32();
        let bytes = if extract_le { val.to_le_bytes() } else { val.to_be_bytes() };
        out.extend_from_slice(&bytes);
    }
    out.truncate(count);
    out
}

fn main() -> Result<()> {
    let log_dir = DEFAULT_LOG_DIR;

    println!("=== ZZZ Decrypt Probe (P1 Validation) ===");
    println!("Target conv:  0x{:08X}", TARGET_CONV);
    println!("Token bytes:  {:02X?}", TOKEN_BYTES);
    println!("Log dir:      {}", log_dir);

    // --- T1.1: Load and filter by conv ---
    let path = Path::new(log_dir);
    let mut entries: Vec<_> = fs::read_dir(path)?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map_or(false, |ext| ext == "bin"))
        .collect();
    entries.sort();

    println!("\n[T1.1] Reading {} .bin files...", entries.len());

    let mut raw_payloads: Vec<Vec<u8>> = Vec::new();
    for entry in &entries {
        let file_bytes = fs::read(entry)?;
        if let Some(payload) = strip_ethernet(&file_bytes) {
            if payload.len() >= 4 {
                let conv = u32::from_le_bytes(payload[0..4].try_into().unwrap());
                if conv == TARGET_CONV {
                    raw_payloads.push(payload);
                }
            }
        }
    }
    println!("[T1.1] Payloads matching conv 0x{:08X}: {}", TARGET_CONV, raw_payloads.len());

    // --- T1.2: Deduplicate by raw bytes ---
    let mut seen: HashSet<Vec<u8>> = HashSet::new();
    let deduped: Vec<Vec<u8>> = raw_payloads
        .into_iter()
        .filter(|p| seen.insert(p.clone()))
        .collect();
    println!("[T1.2] After dedup: {} unique payloads", deduped.len());

    // Diagnostics: count deduped payloads by length and cmd byte
    {
        let mut size_dist: BTreeMap<usize, usize> = BTreeMap::new();
        let mut cmd_dist: BTreeMap<u8, usize> = BTreeMap::new();
        for p in &deduped {
            *size_dist.entry(p.len()).or_insert(0) += 1;
            if p.len() >= 9 { *cmd_dist.entry(p[8]).or_insert(0) += 1; }
        }
        println!("[DIAG] Deduped payload sizes (top 8):");
        let mut size_vec: Vec<_> = size_dist.iter().collect();
        size_vec.sort_by(|a, b| b.1.cmp(a.1));
        for (sz, cnt) in size_vec.iter().take(8) {
            println!("         {} bytes: {} packets", sz, cnt);
        }
        println!("[DIAG] Cmd byte distribution (at offset 8):");
        for (cmd, cnt) in &cmd_dist {
            println!("         cmd=0x{:02X} ({}): {} packets", cmd, cmd, cnt);
        }
        // Show raw bytes of one large packet for inspection
        if let Some(big) = deduped.iter().find(|p| p.len() >= 100) {
            println!("[DIAG] Sample large payload ({} bytes):", big.len());
            for (i, chunk) in big.iter().take(256).collect::<Vec<_>>().chunks(16).enumerate() {
                let hex: Vec<String> = chunk.iter().map(|b| format!("{:02X}", b)).collect();
                let ascii: String = chunk.iter().map(|b| if **b >= 0x20 && **b < 0x7F { **b as char } else { '.' }).collect();
                println!("[DIAG]   {:04X}: {}  |{}|", i * 16, hex.join(" "), ascii);
            }
        }
    }

    // --- T1.3: Parse KCP cmd=81 segments, collect unique by sn ---
    // BTreeMap ensures sn-sorted iteration. Keep first occurrence per sn.
    let mut segments: BTreeMap<u32, KcpSegment> = BTreeMap::new();
    let mut total_parsed = 0usize;
    let mut sn_collisions = 0usize;
    let mut sn_min = u32::MAX;
    let mut sn_max = u32::MIN;
    for payload in &deduped {
        for seg in parse_kcp_data_segments(payload) {
            total_parsed += 1;
            sn_min = sn_min.min(seg.sn);
            sn_max = sn_max.max(seg.sn);
            if segments.contains_key(&seg.sn) {
                sn_collisions += 1;
            }
            segments.entry(seg.sn).or_insert(seg);
        }
    }
    println!("[T1.3] Total segments parsed: {}", total_parsed);
    println!("[T1.3] sn collisions: {}", sn_collisions);
    println!("[T1.3] sn range: {} .. {}", sn_min, sn_max);
    println!("[T1.3] Unique cmd=81 segments: {}", segments.len());

    println!("[T1.3] First 10 segments (sn, frg, data_len):");
    for seg in segments.values().take(10) {
        println!("         sn={:6}, frg={}, data_len={}", seg.sn, seg.frg, seg.data.len());
    }

    // --- T1.4: Reassemble first complete message ---
    // frg counts DOWN to 0; frg==0 is the final fragment of a message.
    // Walk sorted segments; accumulate until we see frg==0.
    let mut current_msg: Vec<(u32, Vec<u8>)> = Vec::new();
    let mut reassembled_body: Option<Vec<u8>> = None;

    for (&sn, seg) in &segments {
        current_msg.push((sn, seg.data.clone()));
        if seg.frg == 0 {
            current_msg.sort_by_key(|(s, _)| *s);
            let body: Vec<u8> = current_msg
                .iter()
                .flat_map(|(_, d)| d.iter().copied())
                .collect();
            reassembled_body = Some(body);
            break;
        }
    }

    let body = match reassembled_body {
        Some(b) if !b.is_empty() => b,
        Some(_) => {
            println!("[T1.4] ERROR: Reassembled body is empty (first frg==0 segment has no data).");
            println!("       The reassembler picked up an empty keepalive/probe segment.");
            println!("       Skipping to first non-empty message...");
            // Find first complete non-empty message by skipping leading empties
            let mut found: Option<Vec<u8>> = None;
            let mut current_msg2: Vec<(u32, Vec<u8>)> = Vec::new();
            let mut skip_until_empty_frg = true;
            for (&sn, seg) in &segments {
                if skip_until_empty_frg {
                    // Skip the first frg==0 empty message we already found
                    if seg.frg == 0 && seg.data.is_empty() {
                        skip_until_empty_frg = false;
                        current_msg2.clear();
                        continue;
                    }
                    if seg.frg == 0 {
                        skip_until_empty_frg = false;
                    }
                    continue;
                }
                current_msg2.push((sn, seg.data.clone()));
                if seg.frg == 0 {
                    current_msg2.sort_by_key(|(s, _)| *s);
                    let b: Vec<u8> = current_msg2.iter().flat_map(|(_, d)| d.iter().copied()).collect();
                    if !b.is_empty() { found = Some(b); break; }
                    current_msg2.clear();
                }
            }
            match found {
                Some(b) => { println!("[T1.4] Found next non-empty message."); b }
                None => { println!("[T1.4] ERROR: No non-empty complete message found."); return Ok(()); }
            }
        }
        None => {
            println!("[T1.4] ERROR: No complete message found (no frg==0 segment).");
            return Ok(());
        }
    };

    let first32_hex: Vec<String> = body.iter().take(32).map(|b| format!("{:02X}", b)).collect();
    println!("[T1.4] Reassembled body: {} bytes", body.len());
    println!("[T1.4] First 32 bytes:   {}", first32_hex.join(" "));

    // Parse the miHoYo frame structure from the first body
    if body.len() >= 12 && body[0..4] == MIHOY_MAGIC {
        let cmd_id = u16::from_be_bytes(body[4..6].try_into().unwrap());
        let head_len = u16::from_be_bytes(body[6..8].try_into().unwrap()) as usize;
        let body_len = u32::from_be_bytes(body[8..12].try_into().unwrap()) as usize;
        println!("[T1.4] miHoYo frame: CmdId=0x{:04X}={}, head_len={}, body_len={}", cmd_id, cmd_id, head_len, body_len);
        let proto_start = 12 + head_len;
        let end_magic_pos = proto_start + body_len;
        if body.len() >= end_magic_pos + 4 {
            let end_magic = &body[end_magic_pos..end_magic_pos + 4];
            let end_magic_hex: Vec<String> = end_magic.iter().map(|b| format!("{:02X}", b)).collect();
            let is_valid_end = end_magic == [0x89, 0xAB, 0xCD, 0xEF];
            println!("[T1.4] End magic at offset {}: {} ({})",
                end_magic_pos, end_magic_hex.join(" "),
                if is_valid_end { "VALID 89ABCDEF" } else { "NOT 89ABCDEF — body may be encrypted" });
            if proto_start < body.len() {
                let proto_first8: Vec<String> = body[proto_start..].iter().take(8).map(|b| format!("{:02X}", b)).collect();
                println!("[T1.4] Proto body first 8 bytes (at frame offset {}): {}", proto_start, proto_first8.join(" "));
            }
        } else {
            println!("[T1.4] WARN: body too short for claimed body_len={}", body_len);
        }
    }

    // Scan first 20 complete messages, show first 8 bytes and note if plaintext
    println!("\n[T1.4] First 20 complete messages (first 8 bytes, is_plaintext):");
    {
        let mut msg_count = 0;
        let mut current: Vec<(u32, Vec<u8>)> = Vec::new();
        for (&sn, seg) in &segments {
            current.push((sn, seg.data.clone()));
            if seg.frg == 0 {
                current.sort_by_key(|(s, _)| *s);
                let msg: Vec<u8> = current.iter().flat_map(|(_, d)| d.iter().copied()).collect();
                let frag_count = current.len();
                current.clear();
                if msg.is_empty() { continue; }
                let first8: Vec<String> = msg.iter().take(8).map(|b| format!("{:02X}", b)).collect();
                let starts_with_magic = msg.len() >= 4 && msg[0..4] == MIHOY_MAGIC;
                println!("  msg{:3}: sn_end={:8}, {} frags, {} bytes, [{}]{}",
                    msg_count, sn, frag_count, msg.len(), first8.join(" "),
                    if starts_with_magic { " <PLAINTEXT>" } else { " <ENCRYPTED?>" });
                msg_count += 1;
                if msg_count >= 20 { break; }
            }
        }
    }

    // --- T1.5: Seed-orientation sweep ---
    // The miHoYo frame header (magic + CmdId + lengths) is plaintext.
    // The proto body (data[12+head_len .. 12+head_len+body_len]) is encrypted.
    // Extract the encrypted proto body to use as ciphertext for the sweep.
    let proto_body: Vec<u8> = if body.len() >= 12 && body[0..4] == MIHOY_MAGIC {
        let head_len = u16::from_be_bytes(body[6..8].try_into().unwrap()) as usize;
        let body_len = u32::from_be_bytes(body[8..12].try_into().unwrap()) as usize;
        let proto_start = 12 + head_len;
        let proto_end = (proto_start + body_len).min(body.len());
        body[proto_start..proto_end].to_vec()
    } else {
        body.clone()
    };

    let token_le = u32::from_le_bytes(TOKEN_BYTES);
    let token_be = u32::from_be_bytes(TOKEN_BYTES);
    let const_val: u32 = 0x499602D2;

    println!("\n[T1.5] token_le_u32 = 0x{:08X}", token_le);
    println!("[T1.5] token_be_u32 = 0x{:08X}", token_be);
    println!("[T1.5] Encrypted proto body: {} bytes, first 8 hex: {}",
        proto_body.len(),
        proto_body.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
    println!("[T1.5] Checking: does XOR with keystream yield valid proto (first byte tag in 0x08..0x7A)?");

    // Valid protobuf first bytes for fields 1-15 with wire types 0,1,2,5
    let valid_proto_first_bytes: std::collections::HashSet<u8> = {
        let mut s = std::collections::HashSet::new();
        for field in 1u8..=15 {
            for wt in [0u8, 1, 2, 5] {
                s.insert((field << 3) | wt);
            }
        }
        s
    };

    // Same-CmdId XOR analysis: if two messages with the same CmdId use a FRESH keystream
    // (restarted per message), XOR of their proto bodies = XOR of their plaintexts.
    // If identical messages, XOR = 0x00 for every byte.
    println!("\n[T1.5] Same-CmdId proto body XOR analysis (fresh-vs-continuous cipher check):");
    {
        // Collect all messages with proto bodies, group by CmdId
        let mut by_cmdid: std::collections::HashMap<u16, Vec<Vec<u8>>> = std::collections::HashMap::new();
        let mut current: Vec<(u32, Vec<u8>)> = Vec::new();
        for (&sn, seg) in &segments {
            current.push((sn, seg.data.clone()));
            if seg.frg == 0 {
                current.sort_by_key(|(s, _)| *s);
                let msg: Vec<u8> = current.iter().flat_map(|(_, d)| d.iter().copied()).collect();
                current.clear();
                if msg.len() >= 12 && msg[0..4] == MIHOY_MAGIC {
                    let cmd_id = u16::from_be_bytes(msg[4..6].try_into().unwrap());
                    let head_len = u16::from_be_bytes(msg[6..8].try_into().unwrap()) as usize;
                    let body_len = u32::from_be_bytes(msg[8..12].try_into().unwrap()) as usize;
                    let proto_start = 12 + head_len;
                    let proto_end = (proto_start + body_len).min(msg.len());
                    if proto_end > proto_start {
                        let pb = msg[proto_start..proto_end].to_vec();
                        by_cmdid.entry(cmd_id).or_default().push(pb);
                    }
                }
            }
        }

        let mut pairs_checked = 0;
        for (cmd_id, bodies) in &by_cmdid {
            if bodies.len() >= 2 {
                let b0 = &bodies[0];
                let b1 = &bodies[1];
                let xor_bytes: Vec<u8> = b0.iter().zip(b1.iter()).map(|(a, b)| a ^ b).collect();
                let zero_count = xor_bytes.iter().filter(|&&b| b == 0).count();
                let total = xor_bytes.len();
                let first8: Vec<String> = xor_bytes.iter().take(8).map(|b| format!("{:02X}", b)).collect();
                println!("  CmdId=0x{:04X} ({} bodies, {} bytes): XOR[0..8]=[{}], zeros={}/{}{}",
                    cmd_id, bodies.len(), total, first8.join(" "), zero_count, total,
                    if zero_count == total { " <IDENTICAL>" } else { "" });
                pairs_checked += 1;
            }
        }
        if pairs_checked == 0 {
            println!("  No same-CmdId pairs found in the 478 unique segments.");
        }
    }

    // Orientation sweep on the proto body.
    // Key insight from monitor.rs GenericMtCipher: Mt64 with seed=u32, bytes extracted BE.
    // If cipher applied to ENTIRE KCP payload, proto body starts after 12+head_len=12 bytes.
    // So try keystream offsets 0 and 12.
    println!("\n[T1.5] Orientation sweep (proto body ciphertext = first 8 bytes: {}):",
        proto_body.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));

    let check_len = proto_body.len().min(40);

    let mut results: Vec<(String, Vec<u8>, bool)> = Vec::new(); // (name, dec_first8, first_byte_valid)

    // GenericMtCipher exact impl: Mt64(seed as u64), BE bytes. Try ks_offset 0 and 12.
    for ks_offset in [0usize, 12] {
        for &(sname, seed_u32) in &[
            ("token_le", token_le),
            ("token_be", token_be),
        ] {
            let ks = keystream_mt64(seed_u32 as u64, false, check_len + ks_offset);
            let dec: Vec<u8> = proto_body[..check_len].iter()
                .zip(ks[ks_offset..].iter()).map(|(b, k)| b ^ k).collect();
            let d0 = dec.first().copied().unwrap_or(0);
            results.push((
                format!("GenericMtCipher({}) ks_offset={}", sname, ks_offset),
                dec.iter().take(8).copied().collect(),
                valid_proto_first_bytes.contains(&d0),
            ));
        }
    }

    // All Mt64 orientations
    let mt64_seeds: &[(&str, u64)] = &[
        ("token_le as u64",           token_le as u64),
        ("token_be as u64",           token_be as u64),
        ("token_le ^ const as u64",   (token_le ^ const_val) as u64),
        ("token_be ^ const as u64",   (token_be ^ const_val) as u64),
    ];
    for &(sname, seed) in mt64_seeds {
        for &(ename, extract_le) in &[("LE", true), ("BE", false)] {
            let ks = keystream_mt64(seed, extract_le, check_len);
            let dec: Vec<u8> = proto_body[..check_len].iter().zip(ks.iter()).map(|(b, k)| b ^ k).collect();
            let d0 = dec.first().copied().unwrap_or(0);
            results.push((format!("Mt64({}) {}", sname, ename), dec.iter().take(8).copied().collect(),
                valid_proto_first_bytes.contains(&d0)));
        }
    }

    // Mt32 orientations
    let mt32_seeds: &[(&str, u32)] = &[
        ("token_le", token_le), ("token_be", token_be),
        ("token_le^const", token_le ^ const_val), ("token_be^const", token_be ^ const_val),
    ];
    for &(sname, seed) in mt32_seeds {
        for &(ename, extract_le) in &[("LE", true), ("BE", false)] {
            let ks = keystream_mt32(seed, extract_le, check_len);
            let dec: Vec<u8> = proto_body[..check_len].iter().zip(ks.iter()).map(|(b, k)| b ^ k).collect();
            let d0 = dec.first().copied().unwrap_or(0);
            results.push((format!("Mt32({}) {}", sname, ename), dec.iter().take(8).copied().collect(),
                valid_proto_first_bytes.contains(&d0)));
        }
    }

    // RC4 orientations (cipher from monitor.rs GenericRc4Cipher)
    let rc4_keys: &[(&str, Vec<u8>)] = &[
        ("token_bytes",          TOKEN_BYTES.to_vec()),
        ("token_bytes_reversed", TOKEN_BYTES.iter().rev().copied().collect()),
        ("token_le_be_bytes",    [token_le.to_le_bytes(), token_be.to_le_bytes()].concat()),
    ];
    for (kname, key) in rc4_keys {
        let ks = rc4_keystream(key, check_len);
        let dec: Vec<u8> = proto_body[..check_len].iter().zip(ks.iter()).map(|(b, k)| b ^ k).collect();
        let d0 = dec.first().copied().unwrap_or(0);
        results.push((format!("RC4({})", kname), dec.iter().take(8).copied().collect(),
            valid_proto_first_bytes.contains(&d0)));
    }

    println!("  {:<48} | {:25} | valid?", "Orientation", "decrypted first 8");
    println!("  {}", "-".repeat(80));
    let mut any_strong = false;
    for (name, dec8, valid) in &results {
        let dec_str: String = dec8.iter().map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" ");
        let mark = if *valid { "YES" } else { "   " };
        println!("  {:<48} | {:25} | {}", name, dec_str, mark);
        if *valid { any_strong = true; }
    }

    println!("\n[T1.5] Ciphertexts for small identical proto bodies (for brute-force seed recovery):");
    {
        // Collect same-CmdId bodies, show first identical group's actual ciphertext
        let mut by_cmdid2: std::collections::BTreeMap<u16, Vec<Vec<u8>>> = std::collections::BTreeMap::new();
        let mut current: Vec<(u32, Vec<u8>)> = Vec::new();
        for (&sn, seg) in &segments {
            current.push((sn, seg.data.clone()));
            if seg.frg == 0 {
                current.sort_by_key(|(s, _)| *s);
                let msg: Vec<u8> = current.iter().flat_map(|(_, d)| d.iter().copied()).collect();
                current.clear();
                if msg.len() >= 12 && msg[0..4] == MIHOY_MAGIC {
                    let cmd_id = u16::from_be_bytes(msg[4..6].try_into().unwrap());
                    let head_len = u16::from_be_bytes(msg[6..8].try_into().unwrap()) as usize;
                    let body_len = u32::from_be_bytes(msg[8..12].try_into().unwrap()) as usize;
                    let proto_start = 12 + head_len;
                    let proto_end = (proto_start + body_len).min(msg.len());
                    if proto_end > proto_start {
                        by_cmdid2.entry(cmd_id).or_default().push(msg[proto_start..proto_end].to_vec());
                    }
                }
            }
        }
        // Show a few identical groups with short bodies (best for brute-force)
        let mut shown = 0;
        for (cmd_id, bodies) in &by_cmdid2 {
            if bodies.len() < 2 { continue; }
            let b0 = &bodies[0];
            let b1 = &bodies[1];
            // At least first two bodies identical — gives us known ciphertext bytes
            if b0 == b1 {
                let identical_count = bodies.iter().filter(|b| *b == b0).count();
                let hex: Vec<String> = b0.iter().map(|b| format!("{:02X}", b)).collect();
                println!("  CmdId=0x{:04X}: {}/{} identical, {} bytes ciphertext: {}",
                    cmd_id, identical_count, bodies.len(), b0.len(), hex.join(" "));
                shown += 1;
                if shown >= 15 { break; }
            }
        }
        // Also show the ciphertext for msg0 (CmdId=5959 = 0x1747 in this session)
        let first8: Vec<String> = proto_body.iter().take(8).map(|b| format!("{:02X}", b)).collect();
        println!("  CmdId=0x{:04X}: first msg ({} bytes), first 8 ciphertext: {}",
            0x1747u16, proto_body.len(), first8.join(" "));
    }

    if !any_strong {
        println!("\n[T1.5] FAIL: No orientation produced a valid-looking protobuf first byte.");
        println!("       Proceeding to Phase 4 brute-force (T4.1).");
    } else {
        println!("\n[T1.5] Some orientations show valid proto byte (weak signal, ~23% random chance).");
        println!("       See same-CmdId XOR analysis above for additional signal.");
    }

    Ok(())
}
