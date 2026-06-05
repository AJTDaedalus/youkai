use std::fmt::{Debug, Display};
use std::collections::BTreeMap;

use anyhow::Error;
use futures::StreamExt;
use futures::stream::FusedStream;

#[cfg(windows)]
use pktmon::filter::{PktMonFilter, TransportProtocol};
#[cfg(windows)]
use pktmon::{Capture, Packet};

pub const PORT_RANGE: (u16, u16) = (20501, 20502);

/// Shuffled KCP Segment Header structure (Zenless Zone Zero format)
#[derive(Debug, Clone)]
pub struct KcpHeader {
    pub conv: u32,
    pub ts: u32,
    pub cmd: u8,
    pub frg: u8,
    pub wnd: u16,
    pub sn: u32,
    pub una: u32,
    pub len: u32,
}

impl KcpHeader {
    /// Attempts to parse a ZZZ KCP header from 28 bytes.
    /// ZZZ uses a 28-byte variant: standard 24-byte KCP fields + 4 unknown bytes at [20..24],
    /// with the payload length field at [24..28] instead of [20..24].
    pub fn parse(bytes: &[u8]) -> Option<Self> {
        if bytes.len() < 28 {
            return None;
        }
        Some(Self {
            conv: u32::from_le_bytes(bytes[0..4].try_into().unwrap()),
            ts: u32::from_le_bytes(bytes[4..8].try_into().unwrap()),
            cmd: bytes[8],
            frg: bytes[9],
            wnd: u16::from_le_bytes(bytes[10..12].try_into().unwrap()),
            sn: u32::from_le_bytes(bytes[12..16].try_into().unwrap()),
            una: u32::from_le_bytes(bytes[16..20].try_into().unwrap()),
            // bytes[20..24] unknown/reserved — skipped
            len: u32::from_le_bytes(bytes[24..28].try_into().unwrap()),
        })
    }
}

/// Simple thread-safe reassembler to reconstruct fragmented packet sequences
pub struct Reassembler {
    fragments: BTreeMap<u32, Vec<u8>>,
}

impl Reassembler {
    pub fn new() -> Self {
        Self {
            fragments: BTreeMap::new(),
        }
    }

    pub fn insert_and_check(&mut self, sn: u32, frg: u8, data: &[u8]) -> Option<Vec<u8>> {
        self.fragments.insert(sn, data.to_vec());

        if frg == 0 {
            let mut complete = Vec::new();
            for (_seq, mut payload) in std::mem::take(&mut self.fragments) {
                complete.append(&mut payload);
            }
            return Some(complete);
        }
        None
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
    /// ZZZ handshake magic constant at bytes [12..16] (big-endian).
    pub const ZZZ_MAGIC: u32 = 0x499602D2;

    /// Attempts to parse a ZZZ connection handshake (SYN-ACK) from raw UDP bytes.
    /// ZZZ handshakes are exactly 20 bytes:
    ///   [0..4]   type marker (0x00000145 = SYN-ACK, 0x000000FF = SYN)
    ///   [4..8]   conv ID (big-endian in SYN-ACK, zero in SYN)
    ///   [8..12]  seed (little-endian)
    ///   [12..16] magic = 0x499602D2 (big-endian)
    ///   [16..20] trailing field
    ///
    /// Only SYN-ACK packets (type 0x00000145) carry a non-zero conv and seed.
    pub fn parse(bytes: &[u8]) -> Option<Self> {
        if bytes.len() < 20 {
            return None;
        }
        let magic = u32::from_be_bytes(bytes[12..16].try_into().unwrap());
        if magic != Self::ZZZ_MAGIC {
            return None;
        }
        let type_marker = u32::from_be_bytes(bytes[0..4].try_into().unwrap());
        // Only process SYN-ACK (server→client), which carries the session seed
        if type_marker != 0x00000145 {
            return None;
        }
        let conv = u32::from_be_bytes(bytes[4..8].try_into().unwrap());
        let seed = u32::from_le_bytes(bytes[8..12].try_into().unwrap());
        Some(Self { conv, magic, seed })
    }
}

#[derive(Debug)]
#[allow(dead_code)]
pub enum CaptureError {
    Filter(Error),
    Capture { has_captured: bool, error: Error },
    CaptureClosed,
    ChannelClosed,
}

impl Display for CaptureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CaptureError::Filter(e) => write!(f, "Filter error: {}", e),
            CaptureError::Capture {
                has_captured,
                error,
            } => write!(
                f,
                "Capture error (has_captured = {}): {}",
                has_captured, error
            ),
            CaptureError::CaptureClosed => write!(f, "Capture closed"),
            CaptureError::ChannelClosed => write!(f, "Channel closed"),
        }
    }
}

pub type Result<T> = std::result::Result<T, CaptureError>;

// ==========================================
// Windows Real Implementation
// ==========================================
#[cfg(windows)]
pub struct PacketCapture {
    stream: Box<dyn FusedStream<Item = Packet> + Unpin + Send>,
}

#[cfg(windows)]
impl PacketCapture {
    pub fn new(all_udp: bool) -> Result<Self> {
        let mut capture = Capture::new().map_err(|e| CaptureError::Capture {
            has_captured: false,
            error: e.into(),
        })?;

        if all_udp {
            let filter = PktMonFilter {
                name: "UDP all".to_string(),
                transport_protocol: Some(TransportProtocol::UDP),
                ..PktMonFilter::default()
            };

            capture
                .add_filter(filter)
                .map_err(|e| CaptureError::Filter(e.into()))?;
        } else {
            let filter = PktMonFilter {
                name: "UDP Filter".to_string(),
                transport_protocol: Some(TransportProtocol::UDP),
                port: PORT_RANGE.0.into(),
                ..PktMonFilter::default()
            };

            capture
                .add_filter(filter)
                .map_err(|e| CaptureError::Filter(e.into()))?;

            let filter = PktMonFilter {
                name: "UDP Filter".to_string(),
                transport_protocol: Some(TransportProtocol::UDP),
                port: PORT_RANGE.1.into(),
                ..PktMonFilter::default()
            };

            capture
                .add_filter(filter)
                .map_err(|e| CaptureError::Filter(e.into()))?;
        }

        Ok(Self {
            stream: Box::new(capture.stream().unwrap().boxed().fuse()),
        })
    }

    pub async fn next_packet(&mut self) -> Result<Vec<u8>> {
        futures::select! {
            packet = self.stream.select_next_some() => {
                Ok(packet.payload.to_vec().clone())
            },
            complete => Err(CaptureError::CaptureClosed),
        }
    }
}

// ==========================================
// Linux/WSL Mock Implementation for Development
// ==========================================
#[cfg(not(windows))]
pub struct PacketCapture;

#[cfg(not(windows))]
impl PacketCapture {
    pub fn new(_all_udp: bool) -> Result<Self> {
        tracing::warn!("Packet capture is only supported on Windows. Running in mock mode on Linux/WSL.");
        Ok(Self)
    }

    pub async fn next_packet(&mut self) -> Result<Vec<u8>> {
        // Mock a passive wait state by sleeping to prevent busy loops
        tokio::time::sleep(tokio::time::Duration::from_secs(3600)).await;
        Err(CaptureError::CaptureClosed)
    }
}
