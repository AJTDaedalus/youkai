use std::collections::HashMap;
use std::fs;
use std::io::{BufWriter, Write};
use std::time::Instant;

use anime_game_data::AnimeGameData;
use anyhow::{Context, Result, anyhow};
use auto_artifactarium::{
    GameCommand, GamePacket, GameSniffer, matches_achievement_packet, matches_avatar_packet,
    matches_item_packet,
};
use base64::prelude::*;
use chrono::prelude::*;
use flate2::read::GzDecoder;
use tokio::sync::{mpsc, watch};
use tokio_util::sync::CancellationToken;

use crate::capture::PacketCapture;
use crate::player_data::PlayerData;
use crate::{APP_ID, AppState, DataUpdated, Message, State};

struct AppStateManager {
    app_state: AppState,
    state_tx: watch::Sender<AppState>,
}

impl AppStateManager {
    fn new(app_state: AppState, state_tx: watch::Sender<AppState>) -> Self {
        Self {
            app_state,
            state_tx,
        }
    }

    pub fn update_app_state(&mut self, state: State) {
        self.app_state.state = state;
        let _ = self.state_tx.send(self.app_state.clone());
    }

    pub fn update_capturing_state(&mut self, capturing: bool) {
        self.app_state.capturing = capturing;
        let _ = self.state_tx.send(self.app_state.clone());
    }

    pub fn update_timestamps(&mut self, updated: DataUpdated) {
        self.app_state.updated = updated;
        let _ = self.state_tx.send(self.app_state.clone());
    }
}

pub struct Monitor {
    app_state: AppStateManager,
    ui_message_rx: mpsc::UnboundedReceiver<Message>,
    log_packet_rx: watch::Receiver<bool>,
    player_data: PlayerData,
    sniffer: GameSniffer,
    capture_cancel_token: Option<CancellationToken>,
    packet_tx: mpsc::UnboundedSender<Vec<u8>>,
    packet_rx: mpsc::UnboundedReceiver<Vec<u8>>,
    reassembler: crate::capture::Reassembler,
    cipher: Box<dyn YoukaiCipher>,
    handshake_state: HandshakeState,
}

impl Monitor {
    pub async fn new(
        state_tx: watch::Sender<AppState>,
        mut ui_message_rx: mpsc::UnboundedReceiver<Message>,
        log_packet_rx: watch::Receiver<bool>,
    ) -> Result<Self> {
        let mut app_state = AppStateManager::new(state_tx.borrow().clone(), state_tx.clone());
        let game_data = get_database(&mut app_state, &mut ui_message_rx).await?;
        let player_data = PlayerData::new(game_data);
        let keys = load_keys()?;
        let sniffer = GameSniffer::new().set_initial_keys(keys);
        let (packet_tx, packet_rx) = mpsc::unbounded_channel();

        let reassembler = crate::capture::Reassembler::new();
        let cipher = Box::new(PassThroughCipher);
        let handshake_state = HandshakeState::Disconnected;

        Ok(Self {
            app_state,
            player_data,
            ui_message_rx,
            log_packet_rx,
            sniffer,
            capture_cancel_token: None,
            packet_tx,
            packet_rx,
            reassembler,
            cipher,
            handshake_state,
        })
    }

    pub async fn run(mut self) {
        self.app_state.update_app_state(State::Main);

        loop {
            #[rustfmt::skip]
                tokio::select! {
                    Some(packet) = self.packet_rx.recv() => self.handle_packet(packet),
                    Some(msg) = self.ui_message_rx.recv() => self.handle_ui_msg(msg),
                }
        }
    }

    fn handle_ui_msg(&mut self, msg: Message) {
        match msg {
            Message::StartCapture(all_udp) => {
                if self.capture_cancel_token.is_some() {
                    tracing::warn!("Capture start request with an existing cancel token");
                }

                // Spawn capture task.
                let cancel_token = CancellationToken::new();
                tokio::spawn(capture_task(cancel_token.clone(), self.packet_tx.clone(), all_udp));
                self.capture_cancel_token = Some(cancel_token);
                self.app_state.update_capturing_state(true);
            }
            Message::StopCapture => {
                let Some(cancel_token) = self.capture_cancel_token.take() else {
                    tracing::warn!("Capture stop request with no current cancel token");
                    return;
                };
                cancel_token.cancel();
                self.app_state.update_capturing_state(false);
            }
            Message::ExportZenlessOptimizer(settings, reply_tx) => {
                let _ = reply_tx.send(self.player_data.export_zenless_optimizer(&settings));
            }
            _ => (),
        }
    }

    fn process_handshake_packet(&mut self, handshake: &crate::capture::HandshakePacket) {
        tracing::info!(
            "Intercepted connection handshake! Session ID 0x{:08X}, seed 0x{:08X}",
            handshake.conv,
            handshake.seed
        );

        // Derive active session cipher dynamically from handshake seed
        let dynamic_cipher = Box::new(GenericMtCipher::new(handshake.seed));
        self.cipher = dynamic_cipher;
        self.handshake_state = HandshakeState::Connected;

        tracing::info!("Dynamic session key successfully bound to Youkai stream cipher pipeline!");
    }

    fn handle_packet(&mut self, packet: Vec<u8>) {
        let log_packets = *self.log_packet_rx.borrow_and_update();

        if log_packets {
            if let Err(e) = log_raw_packet(&packet) {
                tracing::info!("error logging raw ZZZ packet {e}");
            }
        }

        // Auto-detect Layer-2/Layer-3 framing and extract Layer-4 UDP payload
        let mut udp_payload = packet.clone();
        if packet.len() >= 42 && packet[12] == 0x08 && packet[13] == 0x00 {
            let ip_header_len = ((packet[14] & 0x0F) * 4) as usize;
            let ip_proto = packet[23];
            if ip_proto == 17 && packet.len() >= 14 + ip_header_len + 8 {
                let payload_offset = 14 + ip_header_len + 8;
                if packet.len() >= payload_offset {
                    udp_payload = packet[payload_offset..].to_vec();
                }
            }
        }

        // Check for connection handshake first
        if let Some(handshake) = crate::capture::HandshakePacket::parse(&udp_payload) {
            self.process_handshake_packet(&handshake);
            return;
        }

        let mut data = &udp_payload[..];

        while data.len() >= 28 {
            if let Some(header) = crate::capture::KcpHeader::parse(data) {
                let len = header.len as usize;
                if data.len() < 28 + len {
                    break;
                }

                let mut payload = data[28..28 + len].to_vec();
                data = &data[28 + len..]; // Advance pointer

                // Apply generic stream decryption cipher in-place
                self.cipher.decrypt(&mut payload);

                // If KCP command is data push (cmd 81), feed to our reassembler
                if header.cmd == 81 {
                    if let Some(complete_message) = self.reassembler.insert_and_check(header.sn, header.frg, &payload) {
                        tracing::info!(
                            "Reassembled complete gameplay KCP payload: Conversation ID 0x{:08X}, length: {} bytes",
                            header.conv,
                            complete_message.len()
                        );
                        // Strongly-typed deserialization hooks would be placed here
                    }
                }
            } else {
                break;
            }
        }
    }
}

fn log_raw_packet(packet: &[u8]) -> Result<()> {
    let mut packet_log_path = eframe::storage_dir(APP_ID).context("Storage dir not found")?;
    packet_log_path.push("packet_log");
    fs::create_dir_all(&packet_log_path)?;

    let now = Local::now();
    packet_log_path.push(format!(
        "{}-raw.bin",
        now.format("%Y-%m-%d_%H-%M-%S%.f")
    ));

    let file = fs::File::create(&packet_log_path)
        .with_context(|| format!("can't create file {packet_log_path:?}"))?;
    let mut writer = BufWriter::new(file);
    writer.write_all(packet)?;

    Ok(())
}

async fn get_database(
    app_state: &mut AppStateManager,
    _ui_message_rx: &mut mpsc::UnboundedReceiver<Message>,
) -> Result<AnimeGameData> {
    app_state.update_app_state(State::CheckingForData);

    static DATABASE: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/game_data.gz"));
    let reader = GzDecoder::new(DATABASE);
    let db = anime_game_data::AnimeGameData::new_from_reader(reader)?;

    Ok(db)
}

async fn capture_task(
    cancel_token: CancellationToken,
    packet_tx: mpsc::UnboundedSender<Vec<u8>>,
    all_udp: bool,
) -> Result<()> {
    let mut capture =
        PacketCapture::new(all_udp).map_err(|e| anyhow!("Error creating packet capture: {e}"))?;
    tracing::info!("starting capture");
    loop {
        let packet = tokio::select!(
            packet = capture.next_packet() => packet,
            _ = cancel_token.cancelled() => break,
        );
        let packet = match packet {
            Ok(packet) => packet,
            Err(e) => {
                tracing::error!("Error receiving packet: {e}");
                continue;
            }
        };

        if let Err(e) = packet_tx.send(packet) {
            tracing::error!("Error sending captured packet to monitor: {e}");
        }
    }
    tracing::info!("ending capture");
    Ok(())
}

fn log_command(command: &GameCommand) -> Result<()> {
    let mut packet_log_path = eframe::storage_dir(APP_ID).context("Storage dir not found")?;
    packet_log_path.push("packet_log");
    fs::create_dir_all(&packet_log_path)?;

    let now = Local::now();
    packet_log_path.push(format!(
        "{}-{}.bin",
        now.format("%Y-%m-%d_%H-%M-%S%.f"),
        command.command_id
    ));

    let file = fs::File::create(&packet_log_path)
        .with_context(|| format!("can't create file {packet_log_path:?}"))?;
    let mut writer = BufWriter::new(file);
    writer.write_all(&command.proto_data)?;

    Ok(())
}

fn load_keys() -> Result<HashMap<u16, Vec<u8>>> {
    let keys: HashMap<u16, String> = serde_json::from_slice(include_bytes!("../keys/gi.json"))?;

    keys.iter()
        .map(|(key, value)| -> Result<_, _> { Ok((*key, BASE64_STANDARD.decode(value)?)) })
        .collect::<Result<HashMap<_, _>>>()
}

// =========================================================================
// Generic Stream Cipher Layer (Concept & Architectural Framework)
// =========================================================================

pub trait YoukaiCipher: Send + Sync {
    /// Decrypts or encrypts a data buffer in-place
    fn decrypt(&mut self, data: &mut [u8]);
}

/// A default pass-through mock implementation (no encryption bypass)
pub struct PassThroughCipher;

impl YoukaiCipher for PassThroughCipher {
    fn decrypt(&mut self, _data: &mut [u8]) {}
}

/// A generic key-based XOR stream cipher demonstrating basic crypto reassembly
#[allow(dead_code)]
pub struct GenericXorCipher {
    key: Vec<u8>,
}

#[allow(dead_code)]
impl GenericXorCipher {
    pub fn new(key: Vec<u8>) -> Self {
        Self { key }
    }
}

impl YoukaiCipher for GenericXorCipher {
    fn decrypt(&mut self, data: &mut [u8]) {
        if self.key.is_empty() {
            return;
        }
        for (i, byte) in data.iter_mut().enumerate() {
            *byte ^= self.key[i % self.key.len()];
        }
    }
}

/// An abstract, educational implementation of the standard RC4 cipher
#[allow(dead_code)]
pub struct GenericRc4Cipher {
    s: [u8; 256],
    i: usize,
    j: usize,
}

#[allow(dead_code)]
impl GenericRc4Cipher {
    pub fn new(key: &[u8]) -> Self {
        let mut s = [0u8; 256];
        for i in 0..256 {
            s[i] = i as u8;
        }
        let mut j: usize = 0;
        for i in 0..256 {
            if !key.is_empty() {
                j = (j + s[i] as usize + key[i % key.len()] as usize) % 256;
                s.swap(i, j);
            }
        }
        Self { s, i: 0, j: 0 }
    }
}

impl YoukaiCipher for GenericRc4Cipher {
    fn decrypt(&mut self, data: &mut [u8]) {
        for byte in data.iter_mut() {
            self.i = (self.i + 1) % 256;
            self.j = (self.j + self.s[self.i] as usize) % 256;
            self.s.swap(self.i, self.j);
            let t = (self.s[self.i] as usize + self.s[self.j] as usize) % 256;
            *byte ^= self.s[t];
        }
    }
}

/// An abstract, educational stream cipher using standard MT19937 PRNG blocks
#[allow(dead_code)]
pub struct GenericMtCipher {
    mt: rand_mt::Mt64,
    buffer: [u8; 8],
    buffer_idx: usize,
}

#[allow(dead_code)]
impl GenericMtCipher {
    pub fn new(seed: u32) -> Self {
        Self {
            mt: rand_mt::Mt64::new(seed as u64),
            buffer: [0; 8],
            buffer_idx: 8,
        }
    }

    fn next_byte(&mut self) -> u8 {
        if self.buffer_idx >= 8 {
            let block = self.mt.next_u64();
            self.buffer = block.to_be_bytes();
            self.buffer_idx = 0;
        }
        let val = self.buffer[self.buffer_idx];
        self.buffer_idx += 1;
        val
    }
}

impl YoukaiCipher for GenericMtCipher {
    fn decrypt(&mut self, data: &mut [u8]) {
        for byte in data.iter_mut() {
            *byte ^= self.next_byte();
        }
    }
}

// =========================================================================
// Handshake State Tracking Enumeration
// =========================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandshakeState {
    Disconnected,
    Handshaking,
    Connected,
}
