/// T1'.1 — Build known-plaintext prediction model for ZZZ v2.8 token exchange.
///
/// Field tables from nap_generated.zig lines 8650–8659 (ScRsp) and 8822–8840 (CsReq).
/// Outputs: state/v2.8/predictions_csreq.json, state/v2.8/predictions_scrsp.json
///
/// Each entry: { "pos": N, "byte": B, "confidence": F, "field": "name", "kind": "tag|value|length" }
/// Positions where the prediction is absent are unknown (opaque bytes-field content, etc.).
///
/// If T1'.4 validation fails (< 95% tag agreement), first thing to try:
///   - Flip platform_type to 1, 2, or 4  (PLATFORM_TYPE constant below)
///   - Flip channel_id to 2 or 14        (CHANNEL_ID constant below)
///   - Try non-ascending field emission order (permute fields 1-5 and check cross-validate)

use std::fs;
use serde::Serialize;

// ── User-supplied constants ────────────────────────────────────────────────
const UID: u64 = 1000005089;
const CHANNEL_ID: u64 = 1;    // Global. If validation fails: try 2 (CN), 14 (Bili)
const PLATFORM_TYPE: u64 = 3; // Windows PC. If validation fails: try 1, 2, 4

// ── Output paths ───────────────────────────────────────────────────────────
const OUT_CSREQ: &str = "/root/youkai/state/v2.8/predictions_csreq.json";
const OUT_SCRSP: &str = "/root/youkai/state/v2.8/predictions_scrsp.json";

// ── Types ──────────────────────────────────────────────────────────────────

#[derive(Serialize, Debug, Clone)]
struct Prediction {
    pos: usize,
    byte: u8,
    confidence: f32,
    field: &'static str,
    kind: &'static str,
}

/// Encode a u64 as a protobuf varint (little-endian 7-bit groups).
fn varint(mut v: u64) -> Vec<u8> {
    let mut out = Vec::new();
    loop {
        let mut b = (v & 0x7F) as u8;
        v >>= 7;
        if v != 0 {
            b |= 0x80;
        }
        out.push(b);
        if v == 0 {
            break;
        }
    }
    out
}

/// Proto3 tag as a varint: (field_num << 3) | wire_type.
fn tag_bytes(field_num: u32, wire_type: u8) -> Vec<u8> {
    varint(((field_num as u64) << 3) | wire_type as u64)
}

// ── Confidence levels ──────────────────────────────────────────────────────
const CONF_USER:    f32 = 0.99; // User-supplied value (uid, retcode=0, channel, platform)
const CONF_DEFAULT: f32 = 0.85; // Default-zero assumption for control/unknown fields
const CONF_TAG:     f32 = 0.99; // Tag byte is certain if we know the field is emitted
const CONF_LEN:     f32 = 0.85; // Guessed length varint for bytes fields

// ── Field description ──────────────────────────────────────────────────────

enum FieldContent {
    /// Varint field. wire_value = real_value XOR obf_constant.
    /// If real is None, assume real=0, confidence=CONF_DEFAULT.
    /// If obf=0 and real is None: field may be omitted (proto3), skip.
    Varint { obf: u64, real: Option<u64> },
    /// Bytes field with a known/guessed content length.
    /// Tag + length varint predicted; content bytes are unknown (advance position only).
    Bytes { len: usize },
    /// Bytes field with unknown length: emit nothing (can't predict position of following fields).
    BytesUnknown,
    /// Unknown wire type / obf=0 with no known value: skip entirely.
    Skip,
}

struct Field {
    num: u32,
    name: &'static str,
    content: FieldContent,
}

impl Field {
    fn emit(&self, preds: &mut Vec<Prediction>, pos: &mut usize) {
        match &self.content {
            FieldContent::Varint { obf, real } => {
                let (wire_val, conf) = match (obf, real) {
                    (0, None) => return, // proto3 skips default-zero varint
                    (0, Some(0)) => return,
                    (0, Some(v)) => (*v, CONF_USER),
                    (o, None) => (*o, CONF_DEFAULT), // real=0 assumed
                    (o, Some(v)) => (v ^ o, CONF_USER),
                };
                let tbytes = tag_bytes(self.num, 0);
                for b in &tbytes {
                    preds.push(Prediction { pos: *pos, byte: *b, confidence: CONF_TAG, field: self.name, kind: "tag" });
                    *pos += 1;
                }
                for b in varint(wire_val) {
                    preds.push(Prediction { pos: *pos, byte: b, confidence: conf, field: self.name, kind: "value" });
                    *pos += 1;
                }
            }
            FieldContent::Bytes { len } => {
                // proto3 skips empty bytes fields, but any non-empty len means it's emitted
                if *len == 0 {
                    return;
                }
                let tbytes = tag_bytes(self.num, 2);
                for b in &tbytes {
                    preds.push(Prediction { pos: *pos, byte: *b, confidence: CONF_TAG, field: self.name, kind: "tag" });
                    *pos += 1;
                }
                for b in varint(*len as u64) {
                    preds.push(Prediction { pos: *pos, byte: b, confidence: CONF_LEN, field: self.name, kind: "length" });
                    *pos += 1;
                }
                // Content bytes: unknown, just advance position
                *pos += len;
            }
            FieldContent::BytesUnknown | FieldContent::Skip => {
                // Cannot predict; position of subsequent fields is unknown too.
                // Caller must stop collecting predictions once a BytesUnknown is hit.
            }
        }
    }

    fn is_blocking(&self) -> bool {
        matches!(self.content, FieldContent::BytesUnknown)
    }
}

// ── Field tables ───────────────────────────────────────────────────────────

fn csreq_fields() -> Vec<Field> {
    vec![
        Field { num: 1,   name: "UNK_1",                content: FieldContent::Varint { obf: 5135,  real: None } },
        Field { num: 2,   name: "channel_id",            content: FieldContent::Varint { obf: 1615,  real: Some(CHANNEL_ID) } },
        Field { num: 3,   name: "UNK_3",                 content: FieldContent::Varint { obf: 294,   real: None } },
        Field { num: 4,   name: "UNK_4",                 content: FieldContent::Varint { obf: 13101, real: None } },
        Field { num: 5,   name: "platform_type",         content: FieldContent::Varint { obf: 5404,  real: Some(PLATFORM_TYPE) } },
        // field 6: obf=0, type unknown → Skip
        Field { num: 6,   name: "UNK_6",                 content: FieldContent::Skip },
        Field { num: 7,   name: "rsa_ver",               content: FieldContent::Varint { obf: 13844, real: None } },
        // field 8: obf=0, type unknown → Skip
        Field { num: 8,   name: "UNK_8",                 content: FieldContent::Skip },
        // client_rand_key: RSA-2048 encrypted = 256 bytes. Blocks position tracking after this.
        Field { num: 9,   name: "client_rand_key",       content: FieldContent::Bytes { len: 256 } },
        Field { num: 10,  name: "UNK_10",                content: FieldContent::Varint { obf: 1806,  real: None } },
        Field { num: 11,  name: "uid",                   content: FieldContent::Varint { obf: 2707,  real: Some(UID) } },
        // token, device, account_uid: variable-length strings/bytes, unknown length → BytesUnknown blocks
        Field { num: 12,  name: "token",                 content: FieldContent::BytesUnknown },
        Field { num: 13,  name: "device",                content: FieldContent::BytesUnknown },
        Field { num: 14,  name: "UNK_14",                content: FieldContent::Varint { obf: 8018,  real: None } },
        Field { num: 15,  name: "account_uid",           content: FieldContent::BytesUnknown },
        Field { num: 859, name: "UNK_859",               content: FieldContent::Varint { obf: 3496,  real: None } },
    ]
}

fn scrsp_fields() -> Vec<Field> {
    vec![
        Field { num: 2,  name: "blacklist_end_timestamp", content: FieldContent::Varint { obf: 14370, real: None } },
        // sign: RSA-2048 signature = 256 bytes. Confident guess but unverified.
        Field { num: 6,  name: "sign",                    content: FieldContent::Bytes { len: 256 } },
        // retcode: 0 = success (login worked). obf=8921 → wire=8921.
        Field { num: 7,  name: "retcode",                 content: FieldContent::Varint { obf: 8921,  real: Some(0) } },
        // EAFKLOCNICF: unknown length → blocks
        Field { num: 9,  name: "EAFKLOCNICF",             content: FieldContent::BytesUnknown },
        Field { num: 12, name: "uid",                     content: FieldContent::Varint { obf: 2796,  real: Some(UID) } },
        Field { num: 13, name: "blacklist_reason",        content: FieldContent::Varint { obf: 15831, real: None } },
        // server_rand_key: 8-byte u64 (the target value). OQ-v3-2: if 256 bytes instead, escalate.
        Field { num: 15, name: "server_rand_key",         content: FieldContent::Bytes { len: 8 } },
    ]
}

// ── Emission ───────────────────────────────────────────────────────────────

fn build_predictions(fields: Vec<Field>) -> Vec<Prediction> {
    let mut preds = Vec::new();
    let mut pos = 0usize;

    for f in &fields {
        if f.is_blocking() {
            // BytesUnknown: we don't know how many bytes this field takes,
            // so we can't track position for any subsequent fields.
            // Emit nothing and stop.
            eprintln!("  [blocking] field {} ({}) — position tracking ends here", f.num, f.name);
            break;
        }
        f.emit(&mut preds, &mut pos);
    }

    preds
}

fn main() -> anyhow::Result<()> {
    fs::create_dir_all("/root/youkai/state/v2.8")?;

    println!("=== CsReq (cmd 2923) ===");
    let csreq = build_predictions(csreq_fields());
    for p in &csreq {
        println!("  pos={:4}  byte=0x{:02X}  conf={:.2}  {}::{}", p.pos, p.byte, p.confidence, p.field, p.kind);
    }
    let csreq_json = serde_json::to_string_pretty(&csreq)?;
    fs::write(OUT_CSREQ, &csreq_json)?;
    println!("  → {} predictions written to {}", csreq.len(), OUT_CSREQ);

    println!("\n=== ScRsp (cmd 1102) ===");
    let scrsp = build_predictions(scrsp_fields());
    for p in &scrsp {
        println!("  pos={:4}  byte=0x{:02X}  conf={:.2}  {}::{}", p.pos, p.byte, p.confidence, p.field, p.kind);
    }
    let scrsp_json = serde_json::to_string_pretty(&scrsp)?;
    fs::write(OUT_SCRSP, &scrsp_json)?;
    println!("  → {} predictions written to {}", scrsp.len(), OUT_SCRSP);

    Ok(())
}
