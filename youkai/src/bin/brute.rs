use rand_mt::{Mt, Mt64};

// Session 0x0032F714 ciphertexts.
// Cipher is per-message-fresh: each MHY proto body gets a fresh keystream from seed.
// The MHY frame header (magic+CmdId+head_len+body_len) is PLAINTEXT; only proto body is here.
//
// Three short C→S messages (3 bytes each) — fast pre-filter:
const CT_1CD8: [u8; 3] = [0x2A, 0xE4, 0x18]; // CmdId=0x1CD8 (7384), head_len=2
const CT_0794: [u8; 3] = [0x3A, 0xBC, 0x41]; // CmdId=0x0794 (1940), head_len=2
const CT_102A: [u8; 3] = [0x72, 0x81, 0x5D]; // CmdId=0x102A (4138), head_len=2

// Two identical 28-byte C→S messages (sn=2569, sn=2711) — deeper validation:
const CT_061F: [u8; 28] = [
    0x42, 0xC7, 0x5B, 0x7D, 0x92, 0x13, 0x81, 0xE0,
    0x04, 0x89, 0x79, 0xDD, 0x90, 0x09, 0x21, 0x60,
    0xA8, 0xC5, 0x2B, 0x94, 0x21, 0xF9, 0x4C, 0xED,
    0x9C, 0x94, 0xFF, 0xF0,
];

// 538-byte S→C message (sn=1525983302, identical twin at sn=1525983405):
const CT_0DA1: &[u8] = &[
    0x20, 0x28, 0x54, 0xAC, 0x82, 0x0B, 0x2A, 0x01,
    0xBB, 0x3E, 0xBD, 0x55, 0x54, 0x9C, 0xCB, 0x69,
    0xD8, 0xD8, 0x22, 0x38, 0x32, 0xE1, 0xA1, 0x1F,
    0xAC, 0xDF, 0x80, 0x69, 0xEE, 0x4F, 0xE7, 0x2B,
    0x35, 0xA3, 0x37, 0x5A, 0xB0, 0xE0, 0xC0, 0x76,
    0x37, 0xE2, 0xA5, 0x5D, 0x56, 0x07, 0xED, 0x3D,
    0x07, 0xA6, 0x00, 0xE3, 0x4D, 0x2C, 0x6E, 0x45,
    0x7A, 0x88, 0x27, 0x1D, 0xE6, 0x1B, 0x79, 0x98,
    0xF9, 0xE6, 0xE2, 0xA7, 0x33, 0x11, 0xFD, 0x6E,
    0xB0, 0x23, 0xE0, 0xB8, 0xAE, 0x07, 0xAF, 0xCE,
    0xD8, 0x9E, 0x58, 0x46, 0xEE, 0xC0, 0xC3, 0xD0,
    0xB7, 0xC4, 0x4D, 0x47, 0xFF, 0xF2, 0xCF, 0x1C,
    0xE9, 0xEC, 0x45, 0x82, 0xE0, 0x8A, 0x14, 0xE3,
    0x2D, 0x62, 0xDB, 0x19, 0x74, 0xD8, 0x36, 0x35,
    0x27, 0x4E, 0x1A, 0x6D, 0x1D, 0x6D, 0x10, 0x6B,
    0x75, 0x58, 0x01, 0x0F, 0x1B, 0x80, 0xF3, 0x77,
    0x4E, 0xE6, 0x14, 0x97, 0xE5, 0x0E, 0x3F, 0xB4,
    0xC1, 0xF8, 0x3F, 0xE4, 0xF7, 0x3D, 0x5D, 0xCE,
    0x5A, 0x4E, 0xC5, 0x6B, 0x82, 0x38, 0x0A, 0xB1,
    0x0E, 0x99, 0xDD, 0x39, 0xA6, 0x19, 0x4E, 0x6F,
    0xBB, 0x7C, 0x26, 0x53, 0xBF, 0x37, 0xF7, 0x37,
    0xC3, 0xE9, 0x53, 0x26, 0xA0, 0x5D, 0x01, 0x90,
    0x25, 0x78, 0x58, 0x49, 0x7C, 0xCF, 0x79, 0x47,
    0x17, 0xC6, 0x2A, 0x6C, 0xA7, 0x59, 0xE5, 0x08,
    0x69, 0x14, 0x5A, 0x93, 0x82, 0x4F, 0x15, 0x5D,
    0x34, 0xD4, 0xC2, 0x0B, 0xCD, 0x61, 0x4E, 0x82,
    0x4A, 0x7D, 0x4F, 0x3F, 0x72, 0x00, 0x96, 0xBF,
    0xE5, 0x0D, 0x1B, 0x7A, 0xEE, 0x10, 0x61, 0xC2,
    0xD0, 0x23, 0xB2, 0xA5, 0xEE, 0x23, 0x12, 0xC2,
    0xB9, 0xF1, 0xA3, 0x71, 0x4F, 0xCE, 0x7A, 0x36,
    0xE3, 0x8D, 0x1A, 0x66, 0x72, 0x5F, 0xF2, 0xDD,
    0xCB, 0x47, 0xFF, 0x23, 0xA4, 0x67, 0x92, 0x99,
    0x64, 0x2C, 0x3E, 0x3F, 0xF4, 0xF5, 0xFC, 0xD8,
    0x13, 0x5E, 0x92, 0x2F, 0x43, 0xA8, 0xC7, 0xF7,
    0x60, 0x47, 0x56, 0xFC, 0x1F, 0xA9, 0x15, 0xA6,
    0x96, 0x69, 0x1D, 0xB3, 0x87, 0xFB, 0x85, 0xE9,
    0x16, 0x8A, 0x6A, 0x89, 0xC4, 0x5B, 0xCE, 0xAB,
    0x9A, 0x5F, 0x8F, 0x33, 0xF7, 0xBD, 0x33, 0x43,
    0xCC, 0x75, 0xF0, 0x91, 0xDB, 0x2B, 0xE6, 0x4A,
    0xE0, 0x4C, 0x67, 0x61, 0x03, 0x0A, 0x48, 0x2E,
    0x31, 0x91, 0x95, 0x7B, 0x35, 0x58, 0xDA, 0x07,
    0xFD, 0xFC, 0x3F, 0x69, 0xD3, 0x21, 0xA7, 0x86,
    0x01, 0xD7, 0x80, 0xF9, 0x88, 0xA2, 0xC1, 0xE3,
    0xD8, 0x51, 0xBB, 0xA9, 0x32, 0xA0, 0x78, 0x44,
    0xF2, 0x5F, 0x23, 0xD5, 0xE6, 0xE2, 0x6B, 0x9E,
    0x3D, 0x42, 0x5E, 0x13, 0x03, 0xBE, 0x7E, 0xB9,
    0x24, 0xC2, 0xC0, 0xE4, 0xC2, 0x97, 0x89, 0x6B,
    0x74, 0x14, 0x31, 0xC0, 0x1B, 0x6A, 0x06, 0xF0,
    0x53, 0xE6, 0x6D, 0x54, 0x2B, 0x73, 0x2B, 0xD3,
    0xF6, 0x7F, 0xE6, 0x77, 0x22, 0x7E, 0x74, 0xF5,
    0x90, 0x2A, 0x61, 0x1A, 0xF2, 0x6F, 0x35, 0xDF,
    0xB1, 0xEC, 0xC4, 0x0B, 0x74, 0x92, 0x50, 0xE8,
    0xAE, 0x04, 0x80, 0x7E, 0x99, 0x46, 0xBD, 0xE9,
    0xEF, 0xB9, 0x31, 0x67, 0x95, 0x21, 0xDD, 0xE7,
    0x06, 0x2F, 0x86, 0x47, 0x56, 0x10, 0x6B, 0xFD,
    0x2E, 0x3D, 0x4E, 0x93, 0x38, 0xEC, 0x5A, 0x78,
    0x1F, 0xA8, 0x66, 0x7C, 0x3A, 0xFF, 0x60, 0xB9,
    0x07, 0xB7, 0xA1, 0x34, 0x60, 0xC0, 0x70, 0xC5,
    0x27, 0xAE, 0x7A, 0x3D, 0x90, 0x3D, 0xB9, 0x41,
    0x81, 0x11, 0x03, 0x6D, 0xFA, 0x89, 0x8C, 0xAE,
    0x18, 0x38, 0x93, 0xE3, 0x0D, 0xA6, 0xB4, 0x80,
    0x75, 0x89, 0x3B, 0xEB, 0xFD, 0x26, 0x7D, 0x0A,
    0x24, 0xD2, 0xEE, 0x07, 0x56, 0xB7, 0xCA, 0x3F,
    0x58, 0xF9, 0xA1, 0x52, 0x61, 0xF5, 0xAA, 0xE8,
    0x30, 0xAE, 0x1E, 0x0D, 0xD9, 0x9F, 0x80, 0x9C,
    0x69, 0x41, 0xAD, 0x4C, 0xE8, 0xE7, 0x4B, 0x8C,
    0x82, 0xD8, 0xD6, 0x11, 0xC3, 0xFD, 0x2D, 0x36,
    0xD1, 0x30,
];

// 356-byte S→C message (sn=1525982122, head_len=0) — SC cross-validator:
const CT_2591: &[u8] = &[
    0xE8, 0x3D, 0xF8, 0xB0, 0xB0, 0x58, 0xD7, 0x3E,
    0xA5, 0x7B, 0x5A, 0xBE, 0xA6, 0x05, 0x27, 0xA1,
    0xAE, 0x59, 0x21, 0x00, 0xD8, 0x43, 0xC4, 0x17,
    0x90, 0x76, 0x7A, 0x49, 0xEA, 0x13, 0x7C, 0xDE,
    0xD5, 0x3F, 0xDC, 0x08, 0x85, 0x52, 0x7D, 0xCD,
    0x05, 0xBD, 0xBC, 0x88, 0x2C, 0xA7, 0x25, 0x5A,
    0x7B, 0x1E, 0xA9, 0xFF, 0x77, 0x8F, 0x82, 0x91,
    0x38, 0x71, 0x99, 0x12, 0xBD, 0x83, 0x13, 0x91,
    0x02, 0x1D, 0xDD, 0xD3, 0xEC, 0xC5, 0x15, 0x81,
    0xBB, 0x87, 0xC5, 0xF2, 0xB6, 0x93, 0x74, 0x9C,
    0x2F, 0xA8, 0x15, 0x1C, 0x5B, 0xDC, 0xE9, 0x25,
    0x18, 0x6F, 0xFB, 0xEC, 0xF4, 0xB9, 0xE2, 0xA9,
    0x65, 0x87, 0x00, 0xFD, 0x60, 0x64, 0x54, 0x91,
    0xF3, 0x91, 0x47, 0x51, 0xC5, 0xB0, 0x49, 0x1F,
    0x65, 0x63, 0x36, 0x9D, 0x8E, 0x67, 0x48, 0x0F,
    0x69, 0x43, 0xEF, 0x2D, 0xC6, 0x2A, 0xC2, 0xC4,
    0x99, 0xE5, 0xFB, 0x20, 0x7F, 0x02, 0xB3, 0x30,
    0x3F, 0xE4, 0x5F, 0x3A, 0xA1, 0x3D, 0x6B, 0x95,
    0xC9, 0x4F, 0xA3, 0x48, 0x2E, 0x04, 0xFB, 0x8B,
    0xB0, 0x11, 0xD7, 0xA9, 0x29, 0x49, 0x9C, 0xB8,
    0x9D, 0xB4, 0x73, 0xB2, 0x8F, 0x00, 0x72, 0x8C,
    0x33, 0xAF, 0xEF, 0x4A, 0xDF, 0x59, 0xEF, 0x14,
    0xE1, 0xEF, 0xBE, 0xBF, 0x7A, 0x48, 0xEC, 0xCB,
    0x1A, 0xDB, 0x32, 0x9F, 0xC7, 0x32, 0xCE, 0xBB,
    0xC9, 0xCD, 0xE0, 0xE6, 0xB9, 0xF6, 0xED, 0x09,
    0xAE, 0x11, 0xFB, 0x07, 0x42, 0xD5, 0x06, 0x1D,
    0xAC, 0x5E, 0x1B, 0x9C, 0x37, 0x59, 0xFF, 0xF6,
    0xB8, 0x57, 0x2A, 0x08, 0xEF, 0x82, 0x2B, 0x57,
    0x58, 0x58, 0x30, 0x42, 0xDC, 0x1F, 0x51, 0xC7,
    0xFB, 0xE9, 0x05, 0x08, 0x90, 0x1B, 0xB8, 0xE7,
    0x34, 0x04, 0x66, 0x96, 0xE3, 0x56, 0x07, 0x58,
    0x9D, 0x31, 0x9D, 0x59, 0xC4, 0xB1, 0x7E, 0x9E,
    0xA8, 0xB1, 0x87, 0xFE, 0x2D, 0x49, 0x64, 0x11,
    0x71, 0x95, 0xCE, 0x69, 0xD1, 0x76, 0xEE, 0x8D,
    0x83, 0x2F, 0x5C, 0x58, 0xDE, 0x7A, 0x7E, 0xCF,
    0x17, 0xEF, 0xB1, 0x5A, 0xD0, 0x9C, 0x2E, 0x81,
    0x5A, 0xBF, 0x6A, 0x61, 0x1D, 0xE5, 0x6E, 0x39,
    0x83, 0xF3, 0x21, 0x3A, 0xB8, 0x37, 0xBD, 0x66,
    0xEC, 0x3F, 0xF5, 0x51, 0x7D, 0xF8, 0xAB, 0xEE,
    0x28, 0x60, 0x2D, 0x91, 0x4A, 0x5B, 0x41, 0xE2,
    0xE6, 0xA9, 0xA2, 0xDC, 0x10, 0x60, 0xD9, 0xED,
    0x6B, 0x72, 0x4A, 0x0E, 0x0A, 0x31, 0xBF, 0x3A,
    0x59, 0x5E, 0x9C, 0x7F, 0xDD, 0xA2, 0x8F, 0x6B,
    0x3C, 0x23, 0x41, 0x30, 0x0C, 0xEF, 0x40, 0xC7,
    0x5E, 0xD3, 0x04, 0x04,
];

// Valid single-byte proto3 tag: field 1..=15, wire_type 0/1/2/5
fn valid_proto_byte(b: u8) -> bool {
    if b >= 0x80 { return false; }
    let wire = b & 0x07;
    let field = b >> 3;
    field >= 1 && (wire == 0 || wire == 1 || wire == 2 || wire == 5)
}

// Lenient proto3 parser: allows field numbers up to 2^28, skips wire-2 inner content.
// Returns Some(fields) if data fully parses, None if structurally invalid.
fn proto_parse_lenient(data: &[u8]) -> Option<usize> {
    let mut i = 0;
    let mut fields = 0usize;
    while i < data.len() {
        // Read tag varint
        let mut tag = 0u64;
        let mut shift = 0u32;
        loop {
            if i >= data.len() { return None; }
            let b = data[i] as u64;
            i += 1;
            tag |= (b & 0x7F) << shift;
            shift += 7;
            if b < 0x80 { break; }
            if shift > 28 { return None; }
        }
        let wire = (tag & 7) as u8;
        let field = tag >> 3;
        // field 0, implausibly large field numbers (>2048), and wire types 3/4/6/7 are invalid
        if field == 0 || field > 2048 || wire == 3 || wire == 4 || wire >= 6 { return None; }
        fields += 1;
        match wire {
            0 => {
                // varint: consume continuation bytes
                loop {
                    if i >= data.len() { return None; }
                    let b = data[i]; i += 1;
                    if b < 0x80 { break; }
                }
            }
            1 => {
                if i + 8 > data.len() { return None; }
                i += 8;
            }
            2 => {
                // length-delimited: read length varint then skip content
                let mut len = 0usize;
                let mut shift2 = 0u32;
                loop {
                    if i >= data.len() { return None; }
                    let b = data[i] as usize;
                    i += 1;
                    len |= (b & 0x7F) << shift2;
                    shift2 += 7;
                    if (b as u8) < 0x80 { break; }
                    if shift2 > 28 { return None; }
                }
                if i + len > data.len() { return None; }
                i += len; // skip content without recursive validation
            }
            5 => {
                if i + 4 > data.len() { return None; }
                i += 4;
            }
            _ => return None,
        }
    }
    if i == data.len() { Some(fields) } else { None }
}

// Strict proto3 parse: rejects multi-byte tags and wire types 3/4.
// Retained for reference — used as an optional stricter second pass.
fn proto_parse_strict(data: &[u8]) -> Option<usize> {
    let mut i = 0;
    let mut fields = 0usize;
    while i < data.len() {
        let tag = data[i];
        if tag >= 0x80 { return None; }
        let wire = tag & 7;
        let field = tag >> 3;
        if field == 0 || wire == 3 || wire == 4 || wire == 6 || wire == 7 { return None; }
        i += 1;
        fields += 1;
        match wire {
            0 => loop {
                if i >= data.len() { return None; }
                let b = data[i]; i += 1;
                if b < 0x80 { break; }
            },
            1 => {
                if i + 8 > data.len() { return None; }
                i += 8;
            }
            2 => {
                let mut len = 0usize;
                let mut shift = 0usize;
                loop {
                    if i >= data.len() { return None; }
                    let b = data[i] as usize; i += 1;
                    len |= (b & 0x7F) << shift;
                    shift += 7;
                    if b < 0x80 { break; }
                    if shift >= 28 { return None; }
                }
                if i + len > data.len() { return None; }
                i += len;
            }
            5 => {
                if i + 4 > data.len() { return None; }
                i += 4;
            }
            _ => return None,
        }
    }
    if i == data.len() { Some(fields) } else { None }
}

fn xor_slice(ct: &[u8], ks: &[u8]) -> Vec<u8> {
    ct.iter().zip(ks.iter()).map(|(a, b)| a ^ b).collect()
}

// ---- Mt64 BE (GenericMtCipher exact variant) ----
fn brute_mt64_be(valid_ks0: &[bool; 256]) -> usize {
    println!("Brute-forcing Mt64(seed as u64) BE [GenericMtCipher]..."); flush();
    let mut found = 0usize;
    let mut checked = 0u64;
    for seed in 0u32..=u32::MAX {
        let mut mt = Mt64::new(seed as u64);
        let v0 = mt.next_u64().to_be_bytes();

        if !valid_ks0[v0[0] as usize] { continue; }

        // 3-byte checks: first byte + 2 more each
        let p0 = v0[0] ^ CT_1CD8[0];
        let p1 = v0[1] ^ CT_1CD8[1];
        let p2 = v0[2] ^ CT_1CD8[2];
        if proto_parse_lenient(&[p0, p1, p2]).is_none() { continue; }

        let q0 = v0[0] ^ CT_0794[0];
        let q1 = v0[1] ^ CT_0794[1];
        let q2 = v0[2] ^ CT_0794[2];
        if proto_parse_lenient(&[q0, q1, q2]).is_none() { continue; }

        let r0 = v0[0] ^ CT_102A[0];
        let r1 = v0[1] ^ CT_102A[1];
        let r2 = v0[2] ^ CT_102A[2];
        if proto_parse_lenient(&[r0, r1, r2]).is_none() { continue; }

        // 28-byte check on CT_061F
        let mut ks28 = Vec::with_capacity(32);
        ks28.extend_from_slice(&v0);
        let v1 = mt.next_u64().to_be_bytes();
        let v2 = mt.next_u64().to_be_bytes();
        let v3 = mt.next_u64().to_be_bytes();
        ks28.extend_from_slice(&v1);
        ks28.extend_from_slice(&v2);
        ks28.extend_from_slice(&v3);
        let pt_061f = xor_slice(&CT_061F, &ks28[..28]);
        if proto_parse_lenient(&pt_061f).is_none() { continue; }

        // Deep 538-byte check on CT_0DA1
        let mut ks_full = ks28;
        while ks_full.len() < CT_0DA1.len() {
            ks_full.extend_from_slice(&mt.next_u64().to_be_bytes());
        }
        let pt_0da1 = xor_slice(CT_0DA1, &ks_full[..CT_0DA1.len()]);
        let strict = proto_parse_strict(&pt_0da1).is_some();
        let lenient = proto_parse_lenient(&pt_0da1).is_some();
        if lenient {
            println!("  MATCH Mt64-BE seed=0x{:08X} (strict={}):", seed, strict);
            println!("    CT_1CD8 dec: {:02X} {:02X} {:02X}", p0, p1, p2);
            println!("    CT_0794 dec: {:02X} {:02X} {:02X}", q0, q1, q2);
            println!("    CT_102A dec: {:02X} {:02X} {:02X}", r0, r1, r2);
            println!("    CT_061F dec first 8: {}", pt_061f.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
            println!("    CT_0DA1 dec first 8: {}", pt_0da1.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
            flush();
            found += 1;
        } else {
            // C→S validated but S→C (CT_0DA1) failed — indicates key asymmetry or wrong cipher
            // Uncomment to diagnose:
            // eprintln!("  CS_ONLY seed=0x{:08X}", seed);
        }
        checked += 1;
    }
    println!("  Mt64-BE: {} deep checks, {} matches", checked, found); flush();
    found
}

// ---- Mt64 LE ----
fn brute_mt64_le(valid_ks0: &[bool; 256]) -> usize {
    println!("Brute-forcing Mt64(seed as u64) LE..."); flush();
    let mut found = 0usize;
    let mut checked = 0u64;
    for seed in 0u32..=u32::MAX {
        let mut mt = Mt64::new(seed as u64);
        let v0 = mt.next_u64().to_le_bytes();
        if !valid_ks0[v0[0] as usize] { continue; }
        let p0 = v0[0] ^ CT_1CD8[0]; let p1 = v0[1] ^ CT_1CD8[1]; let p2 = v0[2] ^ CT_1CD8[2];
        if proto_parse_lenient(&[p0, p1, p2]).is_none() { continue; }
        let q0 = v0[0] ^ CT_0794[0]; let q1 = v0[1] ^ CT_0794[1]; let q2 = v0[2] ^ CT_0794[2];
        if proto_parse_lenient(&[q0, q1, q2]).is_none() { continue; }
        let r0 = v0[0] ^ CT_102A[0]; let r1 = v0[1] ^ CT_102A[1]; let r2 = v0[2] ^ CT_102A[2];
        if proto_parse_lenient(&[r0, r1, r2]).is_none() { continue; }
        let v1 = mt.next_u64().to_le_bytes();
        let v2 = mt.next_u64().to_le_bytes();
        let v3 = mt.next_u64().to_le_bytes();
        let mut ks28 = Vec::with_capacity(32);
        ks28.extend_from_slice(&v0); ks28.extend_from_slice(&v1); ks28.extend_from_slice(&v2); ks28.extend_from_slice(&v3);
        let pt_061f = xor_slice(&CT_061F, &ks28[..28]);
        if proto_parse_lenient(&pt_061f).is_none() { continue; }
        let mut ks_full = ks28;
        while ks_full.len() < CT_0DA1.len() { ks_full.extend_from_slice(&mt.next_u64().to_le_bytes()); }
        let pt_0da1 = xor_slice(CT_0DA1, &ks_full[..CT_0DA1.len()]);
        if proto_parse_lenient(&pt_0da1).is_some() {
            let strict = proto_parse_strict(&pt_0da1).is_some();
            println!("  MATCH Mt64-LE seed=0x{:08X} (strict={}):", seed, strict);
            println!("    CT_1CD8 dec: {:02X} {:02X} {:02X}", p0, p1, p2);
            println!("    CT_061F dec first 8: {}", pt_061f.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
            println!("    CT_0DA1 dec first 8: {}", pt_0da1.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
            found += 1;
        }
        checked += 1;
    }
    println!("  Mt64-LE: {} deep checks, {} matches", checked, found); flush();
    found
}

// ---- Mt32 BE ----
fn brute_mt32_be(valid_ks0: &[bool; 256]) -> usize {
    println!("Brute-forcing Mt32(seed) BE..."); flush();
    let mut found = 0usize;
    let mut checked = 0u64;
    for seed in 0u32..=u32::MAX {
        let mut mt = Mt::new(seed);
        let v0 = mt.next_u32().to_be_bytes();
        if !valid_ks0[v0[0] as usize] { continue; }
        let p0 = v0[0] ^ CT_1CD8[0]; let p1 = v0[1] ^ CT_1CD8[1]; let p2 = v0[2] ^ CT_1CD8[2];
        if proto_parse_lenient(&[p0, p1, p2]).is_none() { continue; }
        let q0 = v0[0] ^ CT_0794[0]; let q1 = v0[1] ^ CT_0794[1]; let q2 = v0[2] ^ CT_0794[2];
        if proto_parse_lenient(&[q0, q1, q2]).is_none() { continue; }
        let r0 = v0[0] ^ CT_102A[0]; let r1 = v0[1] ^ CT_102A[1]; let r2 = v0[2] ^ CT_102A[2];
        if proto_parse_lenient(&[r0, r1, r2]).is_none() { continue; }
        // Mt32 produces 4 bytes per call; 28 bytes needs 7 calls
        let v1 = mt.next_u32().to_be_bytes();
        let v2 = mt.next_u32().to_be_bytes();
        let v3 = mt.next_u32().to_be_bytes();
        let v4 = mt.next_u32().to_be_bytes();
        let v5 = mt.next_u32().to_be_bytes();
        let v6 = mt.next_u32().to_be_bytes();
        let mut ks28 = Vec::with_capacity(28);
        ks28.extend_from_slice(&v0); ks28.extend_from_slice(&v1); ks28.extend_from_slice(&v2);
        ks28.extend_from_slice(&v3); ks28.extend_from_slice(&v4); ks28.extend_from_slice(&v5);
        ks28.extend_from_slice(&v6);
        let pt_061f = xor_slice(&CT_061F, &ks28[..28]);
        if proto_parse_lenient(&pt_061f).is_none() { continue; }
        let mut ks_full = ks28;
        while ks_full.len() < CT_0DA1.len() { ks_full.extend_from_slice(&mt.next_u32().to_be_bytes()); }
        let pt_0da1 = xor_slice(CT_0DA1, &ks_full[..CT_0DA1.len()]);
        if proto_parse_lenient(&pt_0da1).is_some() {
            println!("  MATCH Mt32-BE seed=0x{:08X}", seed);
            println!("    CT_1CD8 dec: {:02X} {:02X} {:02X}", p0, p1, p2);
            println!("    CT_0DA1 dec first 8: {}", pt_0da1.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
            found += 1;
        }
        checked += 1;
    }
    println!("  Mt32-BE: {} deep checks, {} matches", checked, found); flush();
    found
}

// ---- Mt32 LE ----
fn brute_mt32_le(valid_ks0: &[bool; 256]) -> usize {
    println!("Brute-forcing Mt32(seed) LE..."); flush();
    let mut found = 0usize;
    let mut checked = 0u64;
    for seed in 0u32..=u32::MAX {
        let mut mt = Mt::new(seed);
        let v0 = mt.next_u32().to_le_bytes();
        if !valid_ks0[v0[0] as usize] { continue; }
        let p0 = v0[0] ^ CT_1CD8[0]; let p1 = v0[1] ^ CT_1CD8[1]; let p2 = v0[2] ^ CT_1CD8[2];
        if proto_parse_lenient(&[p0, p1, p2]).is_none() { continue; }
        let q0 = v0[0] ^ CT_0794[0]; let q1 = v0[1] ^ CT_0794[1]; let q2 = v0[2] ^ CT_0794[2];
        if proto_parse_lenient(&[q0, q1, q2]).is_none() { continue; }
        let r0 = v0[0] ^ CT_102A[0]; let r1 = v0[1] ^ CT_102A[1]; let r2 = v0[2] ^ CT_102A[2];
        if proto_parse_lenient(&[r0, r1, r2]).is_none() { continue; }
        let v1 = mt.next_u32().to_le_bytes();
        let v2 = mt.next_u32().to_le_bytes();
        let v3 = mt.next_u32().to_le_bytes();
        let v4 = mt.next_u32().to_le_bytes();
        let v5 = mt.next_u32().to_le_bytes();
        let v6 = mt.next_u32().to_le_bytes();
        let mut ks28 = Vec::with_capacity(28);
        ks28.extend_from_slice(&v0); ks28.extend_from_slice(&v1); ks28.extend_from_slice(&v2);
        ks28.extend_from_slice(&v3); ks28.extend_from_slice(&v4); ks28.extend_from_slice(&v5);
        ks28.extend_from_slice(&v6);
        let pt_061f = xor_slice(&CT_061F, &ks28[..28]);
        if proto_parse_lenient(&pt_061f).is_none() { continue; }
        let mut ks_full = ks28;
        while ks_full.len() < CT_0DA1.len() { ks_full.extend_from_slice(&mt.next_u32().to_le_bytes()); }
        let pt_0da1 = xor_slice(CT_0DA1, &ks_full[..CT_0DA1.len()]);
        if proto_parse_lenient(&pt_0da1).is_some() {
            println!("  MATCH Mt32-LE seed=0x{:08X}", seed);
            println!("    CT_1CD8 dec: {:02X} {:02X} {:02X}", p0, p1, p2);
            println!("    CT_0DA1 dec first 8: {}", pt_0da1.iter().take(8).map(|b| format!("{:02X}", b)).collect::<Vec<_>>().join(" "));
            found += 1;
        }
        checked += 1;
    }
    println!("  Mt32-LE: {} deep checks, {} matches", checked, found); flush();
    found
}

fn flush() { let _ = std::io::Write::flush(&mut std::io::stdout()); }

// ---- S→C only brutes: validates CT_0DA1 (538B) then cross-validates CT_2591 (356B) ----
// Two-step: 32-byte quick filter first (cheap), then full 538B, then CT_2591 cross-validate.
// CT_0DA1 and CT_2591 must both parse as valid proto3 for the same seed → near-zero false positives.

fn sc_check_mt64_be(seed: u32, valid_ks0: &[bool; 256]) -> Option<([u8; 16], [u8; 16])> {
    let mut mt = Mt64::new(seed as u64);
    let v0 = mt.next_u64().to_be_bytes();
    if !valid_ks0[v0[0] as usize] { return None; }
    // Quick: first 32 bytes of CT_0DA1
    let mut ks32 = [0u8; 32];
    ks32[..8].copy_from_slice(&v0);
    for i in (8..32).step_by(8) { mt.next_u64().to_be_bytes().iter().enumerate().for_each(|(j,&b)| ks32[i+j]=b); }
    let quick: Vec<u8> = CT_0DA1[..32].iter().zip(ks32.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&quick).is_none() { return None; }
    // Full CT_0DA1 (538B)
    let mut ks = Vec::with_capacity(544);
    ks.extend_from_slice(&ks32);
    while ks.len() < CT_0DA1.len() { mt.next_u64().to_be_bytes().iter().for_each(|&b| ks.push(b)); }
    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt0).is_none() { return None; }
    // Cross-validate CT_2591 (356B) with fresh MT
    let mut mt2 = Mt64::new(seed as u64);
    let mut ks2 = Vec::with_capacity(360);
    while ks2.len() < CT_2591.len() { mt2.next_u64().to_be_bytes().iter().for_each(|&b| ks2.push(b)); }
    let pt1: Vec<u8> = CT_2591.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt1).is_none() { return None; }
    let mut h0 = [0u8; 16]; h0.copy_from_slice(&pt0[..16]);
    let mut h1 = [0u8; 16]; h1.copy_from_slice(&pt1[..16]);
    Some((h0, h1))
}

fn sc_check_mt64_le(seed: u32, valid_ks0: &[bool; 256]) -> Option<([u8; 16], [u8; 16])> {
    let mut mt = Mt64::new(seed as u64);
    let v0 = mt.next_u64().to_le_bytes();
    if !valid_ks0[v0[0] as usize] { return None; }
    let mut ks32 = [0u8; 32];
    ks32[..8].copy_from_slice(&v0);
    for i in (8..32).step_by(8) { mt.next_u64().to_le_bytes().iter().enumerate().for_each(|(j,&b)| ks32[i+j]=b); }
    let quick: Vec<u8> = CT_0DA1[..32].iter().zip(ks32.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&quick).is_none() { return None; }
    let mut ks = Vec::with_capacity(544);
    ks.extend_from_slice(&ks32);
    while ks.len() < CT_0DA1.len() { mt.next_u64().to_le_bytes().iter().for_each(|&b| ks.push(b)); }
    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt0).is_none() { return None; }
    let mut mt2 = Mt64::new(seed as u64);
    let mut ks2 = Vec::with_capacity(360);
    while ks2.len() < CT_2591.len() { mt2.next_u64().to_le_bytes().iter().for_each(|&b| ks2.push(b)); }
    let pt1: Vec<u8> = CT_2591.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt1).is_none() { return None; }
    let mut h0 = [0u8; 16]; h0.copy_from_slice(&pt0[..16]);
    let mut h1 = [0u8; 16]; h1.copy_from_slice(&pt1[..16]);
    Some((h0, h1))
}

fn sc_check_mt32_be(seed: u32, valid_ks0: &[bool; 256]) -> Option<([u8; 16], [u8; 16])> {
    let mut mt = Mt::new(seed);
    let v0 = mt.next_u32().to_be_bytes();
    if !valid_ks0[v0[0] as usize] { return None; }
    let mut ks32 = [0u8; 32];
    ks32[..4].copy_from_slice(&v0);
    for i in (4..32).step_by(4) { mt.next_u32().to_be_bytes().iter().enumerate().for_each(|(j,&b)| ks32[i+j]=b); }
    let quick: Vec<u8> = CT_0DA1[..32].iter().zip(ks32.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&quick).is_none() { return None; }
    let mut ks = Vec::with_capacity(544);
    ks.extend_from_slice(&ks32);
    while ks.len() < CT_0DA1.len() { mt.next_u32().to_be_bytes().iter().for_each(|&b| ks.push(b)); }
    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt0).is_none() { return None; }
    let mut mt2 = Mt::new(seed);
    let mut ks2 = Vec::with_capacity(360);
    while ks2.len() < CT_2591.len() { mt2.next_u32().to_be_bytes().iter().for_each(|&b| ks2.push(b)); }
    let pt1: Vec<u8> = CT_2591.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt1).is_none() { return None; }
    let mut h0 = [0u8; 16]; h0.copy_from_slice(&pt0[..16]);
    let mut h1 = [0u8; 16]; h1.copy_from_slice(&pt1[..16]);
    Some((h0, h1))
}

fn sc_check_mt32_le(seed: u32, valid_ks0: &[bool; 256]) -> Option<([u8; 16], [u8; 16])> {
    let mut mt = Mt::new(seed);
    let v0 = mt.next_u32().to_le_bytes();
    if !valid_ks0[v0[0] as usize] { return None; }
    let mut ks32 = [0u8; 32];
    ks32[..4].copy_from_slice(&v0);
    for i in (4..32).step_by(4) { mt.next_u32().to_le_bytes().iter().enumerate().for_each(|(j,&b)| ks32[i+j]=b); }
    let quick: Vec<u8> = CT_0DA1[..32].iter().zip(ks32.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&quick).is_none() { return None; }
    let mut ks = Vec::with_capacity(544);
    ks.extend_from_slice(&ks32);
    while ks.len() < CT_0DA1.len() { mt.next_u32().to_le_bytes().iter().for_each(|&b| ks.push(b)); }
    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt0).is_none() { return None; }
    let mut mt2 = Mt::new(seed);
    let mut ks2 = Vec::with_capacity(360);
    while ks2.len() < CT_2591.len() { mt2.next_u32().to_le_bytes().iter().for_each(|&b| ks2.push(b)); }
    let pt1: Vec<u8> = CT_2591.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
    if proto_parse_lenient(&pt1).is_none() { return None; }
    let mut h0 = [0u8; 16]; h0.copy_from_slice(&pt0[..16]);
    let mut h1 = [0u8; 16]; h1.copy_from_slice(&pt1[..16]);
    Some((h0, h1))
}

fn brute_sc_mt64_be(valid_ks0: &[bool; 256]) -> usize {
    println!("S\u{2192}C-only: Brute Mt64(seed as u64) BE (CT_0DA1 + CT_2591 cross-validate)..."); flush();
    let mut found = 0usize;
    for seed in 0u32..=u32::MAX {
        if let Some((h0, h1)) = sc_check_mt64_be(seed, valid_ks0) {
            println!("  MATCH SC Mt64-BE seed=0x{:08X}", seed);
            println!("    CT_0DA1 dec[0..16]: {}", h0.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            println!("    CT_2591 dec[0..16]: {}", h1.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            flush();
            found += 1;
        }
    }
    println!("  SC Mt64-BE done: {} matches", found); flush();
    found
}

fn brute_sc_mt64_le(valid_ks0: &[bool; 256]) -> usize {
    println!("S\u{2192}C-only: Brute Mt64(seed as u64) LE (CT_0DA1 + CT_2591 cross-validate)..."); flush();
    let mut found = 0usize;
    for seed in 0u32..=u32::MAX {
        if let Some((h0, h1)) = sc_check_mt64_le(seed, valid_ks0) {
            println!("  MATCH SC Mt64-LE seed=0x{:08X}", seed);
            println!("    CT_0DA1 dec[0..16]: {}", h0.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            println!("    CT_2591 dec[0..16]: {}", h1.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            flush();
            found += 1;
        }
    }
    println!("  SC Mt64-LE done: {} matches", found); flush();
    found
}

fn brute_sc_mt32_be(valid_ks0: &[bool; 256]) -> usize {
    println!("S\u{2192}C-only: Brute Mt32(seed) BE (CT_0DA1 + CT_2591 cross-validate)..."); flush();
    let mut found = 0usize;
    for seed in 0u32..=u32::MAX {
        if let Some((h0, h1)) = sc_check_mt32_be(seed, valid_ks0) {
            println!("  MATCH SC Mt32-BE seed=0x{:08X}", seed);
            println!("    CT_0DA1 dec[0..16]: {}", h0.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            println!("    CT_2591 dec[0..16]: {}", h1.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            flush();
            found += 1;
        }
    }
    println!("  SC Mt32-BE done: {} matches", found); flush();
    found
}

fn brute_sc_mt32_le(valid_ks0: &[bool; 256]) -> usize {
    println!("S\u{2192}C-only: Brute Mt32(seed) LE (CT_0DA1 + CT_2591 cross-validate)..."); flush();
    let mut found = 0usize;
    for seed in 0u32..=u32::MAX {
        if let Some((h0, h1)) = sc_check_mt32_le(seed, valid_ks0) {
            println!("  MATCH SC Mt32-LE seed=0x{:08X}", seed);
            println!("    CT_0DA1 dec[0..16]: {}", h0.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            println!("    CT_2591 dec[0..16]: {}", h1.iter().map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
            flush();
            found += 1;
        }
    }
    println!("  SC Mt32-LE done: {} matches", found); flush();
    found
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mode = args.windows(2)
        .find(|w| w[0] == "--mode")
        .map(|w| w[1].as_str())
        .unwrap_or("joint");

    match mode {
        "gi" => {
            // Double-Mt64 key derivation (GI new_key_from_seed style):
            //   inner = Mt64(outer_seed as u64).next_u64()
            //   gen   = Mt64(inner), skip first output → generate 4096-byte key
            // Tests whether the session cipher uses this construction with a 32-bit outer seed.
            // K[0] wire filter: (key[0] XOR ct[0]) & 7 must be in {0,1,2,5} for ALL known CTs.
            // All known CT first bytes have bottom 3 bits ∈ {0, 2}, so intersection = key[0]&7 ∈ {0,2}.
            println!("=== GI-style double-Mt64 brute (32-bit outer seed) ===");
            println!("CT_0DA1 ({} bytes) + CT_2591 ({} bytes) cross-validate", CT_0DA1.len(), CT_2591.len());
            let mut valid_gi_k0 = [false; 256];
            for k in 0..256usize { valid_gi_k0[k] = (k & 7) == 0 || (k & 7) == 2; }
            let vc = valid_gi_k0.iter().filter(|v| **v).count();
            println!("GI K[0] wire filter: {}/256 ({:.1}%) valid", vc, vc as f64/256.0*100.0);
            flush();

            let mut found = 0usize;
            for outer in 0u32..=u32::MAX {
                let inner = Mt64::new(outer as u64).next_u64();
                let mut rng = Mt64::new(inner);
                let _ = rng.next_u64(); // skip first

                // First key u64 → key[0..8]
                let k0u = rng.next_u64().to_be_bytes();
                if !valid_gi_k0[k0u[0] as usize] { continue; }

                // Generate full CT_0DA1 key (538 bytes)
                let mut ks = Vec::with_capacity(544);
                ks.extend_from_slice(&k0u);
                while ks.len() < CT_0DA1.len() { ks.extend_from_slice(&rng.next_u64().to_be_bytes()); }
                let pt0: Vec<u8> = CT_0DA1.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                if proto_parse_lenient(&pt0).is_none() { continue; }

                // Cross-validate CT_2591 with fresh generator
                let mut gen2 = Mt64::new(Mt64::new(outer as u64).next_u64());
                let _ = gen2.next_u64();
                let mut ks2 = Vec::with_capacity(360);
                while ks2.len() < CT_2591.len() { ks2.extend_from_slice(&gen2.next_u64().to_be_bytes()); }
                let pt1: Vec<u8> = CT_2591.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                if proto_parse_lenient(&pt1).is_none() { continue; }

                println!("  MATCH GI outer_seed=0x{:08X} inner=0x{:016X}", outer, inner);
                println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                println!("    CT_2591 dec[0..16]: {}", pt1.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                flush();
                found += 1;
            }
            println!("\n=== GI Summary: {} match(es) ===", found);
            if found == 0 {
                println!("FAIL: Double-Mt64 with 32-bit outer seed does not decrypt session 0x0032F714.");
            }
        }
        "kpa" => {
            // Known-Plaintext Attack brute: CT_2591 is GetPlayerTokenRsp (first S→C).
            // predictions_scrsp.json gives high-confidence plaintext bytes:
            //   PT_2591[0]=0x10 → k[0] = CT_2591[0]^0x10 = 0xE8^0x10 = 0xF8
            //   PT_2591[3]=0x32 → k[3] = CT_2591[3]^0x32 = 0xB0^0x32 = 0x82
            //   PT_2591[262]=0x38 → k[262] = CT_2591[262]^0x38 = 0x64^0x38 = 0x5C
            // k[0]=0xF8 & k[3]=0x82 together pass ~1/65536 seeds — near-zero overhead.
            // This replaces the broken valid_proto_byte filter that rejected the correct key.
            const KPA_K0: u8 = 0xF8;
            const KPA_K3: u8 = 0x82;
            const KPA_K262: u8 = 0x5C;

            println!("=== KPA brute: session 0x0032F714 ===");
            println!("Known keystream: k[0]=0x{:02X} k[3]=0x{:02X} k[262]=0x{:02X}", KPA_K0, KPA_K3, KPA_K262);
            println!("Filter: 1/65536 seeds pass k[0]&&k[3] — ~65K deep checks expected");
            println!("CT_2591 ({} bytes) primary + CT_0DA1 ({} bytes) cross-validate", CT_2591.len(), CT_0DA1.len());
            flush();

            let mut total = 0usize;

            // -- Mt64 BE --
            {
                println!("\nKPA Mt64-BE: k[0]=0x{:02X} k[3]=0x{:02X}...", KPA_K0, KPA_K3); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt64::new(seed as u64);
                    let v0 = mt.next_u64().to_be_bytes();
                    if v0[0] != KPA_K0 || v0[3] != KPA_K3 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u64().to_be_bytes()); }
                    if ks[262] != KPA_K262 { continue; }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt64::new(seed as u64);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u64().to_be_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA Mt64-BE seed=0x{:08X} (strict={})", seed, proto_parse_strict(&pt0).is_some());
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA Mt64-BE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }

            // -- Mt64 LE --
            {
                println!("\nKPA Mt64-LE: k[0]=0x{:02X} k[3]=0x{:02X}...", KPA_K0, KPA_K3); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt64::new(seed as u64);
                    let v0 = mt.next_u64().to_le_bytes();
                    if v0[0] != KPA_K0 || v0[3] != KPA_K3 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u64().to_le_bytes()); }
                    if ks[262] != KPA_K262 { continue; }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt64::new(seed as u64);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u64().to_le_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA Mt64-LE seed=0x{:08X} (strict={})", seed, proto_parse_strict(&pt0).is_some());
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA Mt64-LE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }

            // -- Mt32 BE --
            {
                println!("\nKPA Mt32-BE: k[0]=0x{:02X} k[3]=0x{:02X}...", KPA_K0, KPA_K3); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt::new(seed);
                    let v0 = mt.next_u32().to_be_bytes();
                    if v0[0] != KPA_K0 || v0[3] != KPA_K3 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u32().to_be_bytes()); }
                    if ks[262] != KPA_K262 { continue; }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt::new(seed);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u32().to_be_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA Mt32-BE seed=0x{:08X} (strict={})", seed, proto_parse_strict(&pt0).is_some());
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA Mt32-BE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }

            // -- Mt32 LE --
            {
                println!("\nKPA Mt32-LE: k[0]=0x{:02X} k[3]=0x{:02X}...", KPA_K0, KPA_K3); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt::new(seed);
                    let v0 = mt.next_u32().to_le_bytes();
                    if v0[0] != KPA_K0 || v0[3] != KPA_K3 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u32().to_le_bytes()); }
                    if ks[262] != KPA_K262 { continue; }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt::new(seed);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u32().to_le_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA Mt32-LE seed=0x{:08X} (strict={})", seed, proto_parse_strict(&pt0).is_some());
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA Mt32-LE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }

            println!("\n=== KPA Summary: {} match(es) ===", total);
            if total == 0 {
                println!("FAIL: No 32-bit seed for any MT variant produces keystream k[0]=0xF8,k[3]=0x82.");
                println!("Either the seed space is larger, or ZZZ uses a non-MT cipher/derivation.");
            }
        }
        "kpa1" => {
            // Single-byte KPA: only filter on k[0]=0xF8 (1/256 seeds), skipping k[3] filter.
            // Fallback if predictions_scrsp.json pos 3 prediction is wrong.
            // ~16M seeds pass the filter; each gets full CT_2591 + CT_0DA1 proto3 validation.
            const KPA_K0: u8 = 0xF8;
            println!("=== KPA1 brute (k[0]-only filter): session 0x0032F714 ===");
            println!("Known keystream: k[0]=0x{:02X} only (1/256 filter)", KPA_K0);
            println!("CT_2591 ({} bytes) primary + CT_0DA1 ({} bytes) cross-validate", CT_2591.len(), CT_0DA1.len());
            flush();

            let mut total = 0usize;

            // -- Mt64 BE --
            {
                println!("\nKPA1 Mt64-BE..."); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt64::new(seed as u64);
                    let v0 = mt.next_u64().to_be_bytes();
                    if v0[0] != KPA_K0 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u64().to_be_bytes()); }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt64::new(seed as u64);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u64().to_be_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA1 Mt64-BE seed=0x{:08X}", seed);
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA1 Mt64-BE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }
            // -- Mt64 LE --
            {
                println!("\nKPA1 Mt64-LE..."); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt64::new(seed as u64);
                    let v0 = mt.next_u64().to_le_bytes();
                    if v0[0] != KPA_K0 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u64().to_le_bytes()); }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt64::new(seed as u64);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u64().to_le_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA1 Mt64-LE seed=0x{:08X}", seed);
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA1 Mt64-LE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }
            // -- Mt32 BE --
            {
                println!("\nKPA1 Mt32-BE..."); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt::new(seed);
                    let v0 = mt.next_u32().to_be_bytes();
                    if v0[0] != KPA_K0 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u32().to_be_bytes()); }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt::new(seed);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u32().to_be_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA1 Mt32-BE seed=0x{:08X}", seed);
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA1 Mt32-BE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }
            // -- Mt32 LE --
            {
                println!("\nKPA1 Mt32-LE..."); flush();
                let mut found = 0usize;
                let mut passed = 0u64;
                for seed in 0u32..=u32::MAX {
                    let mut mt = Mt::new(seed);
                    let v0 = mt.next_u32().to_le_bytes();
                    if v0[0] != KPA_K0 { continue; }
                    passed += 1;
                    let mut ks = Vec::with_capacity(360);
                    ks.extend_from_slice(&v0);
                    while ks.len() < CT_2591.len() { ks.extend_from_slice(&mt.next_u32().to_le_bytes()); }
                    let pt2: Vec<u8> = CT_2591.iter().zip(ks.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt2).is_none() { continue; }
                    let mut mt2 = Mt::new(seed);
                    let mut ks2 = Vec::with_capacity(544);
                    while ks2.len() < CT_0DA1.len() { ks2.extend_from_slice(&mt2.next_u32().to_le_bytes()); }
                    let pt0: Vec<u8> = CT_0DA1.iter().zip(ks2.iter()).map(|(a,b)| a^b).collect();
                    if proto_parse_lenient(&pt0).is_none() { continue; }
                    println!("  MATCH KPA1 Mt32-LE seed=0x{:08X}", seed);
                    println!("    CT_2591 dec[0..16]: {}", pt2.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    println!("    CT_0DA1 dec[0..16]: {}", pt0.iter().take(16).map(|b| format!("{:02X}",b)).collect::<Vec<_>>().join(" "));
                    flush(); found += 1;
                }
                println!("  KPA1 Mt32-LE done: {} filter-pass, {} matches", passed, found); flush();
                total += found;
            }

            println!("\n=== KPA1 Summary: {} match(es) ===", total);
            if total == 0 {
                println!("FAIL: No 32-bit seed for any MT variant produces k[0]=0xF8 + valid proto3 on CT_2591+CT_0DA1.");
            }
        }
        "sc" => {
            // S→C only: find the server→client session key using CT_0DA1
            println!("=== S\u{2192}C-only brute: session 0x0032F714, CT_0DA1 ({} bytes) ===", CT_0DA1.len());
            let mut valid_ks0_sc = [false; 256];
            for k in 0..256usize { valid_ks0_sc[k] = valid_proto_byte(k as u8 ^ CT_0DA1[0]); }
            let vc = valid_ks0_sc.iter().filter(|v| **v).count();
            println!("SC K[0] filter: {}/256 ({:.1}%) valid for CT_0DA1[0]=0x{:02X}", vc, vc as f64/256.0*100.0, CT_0DA1[0]);
            flush();
            let mut total = 0;
            total += brute_sc_mt64_be(&valid_ks0_sc);
            total += brute_sc_mt64_le(&valid_ks0_sc);
            total += brute_sc_mt32_be(&valid_ks0_sc);
            total += brute_sc_mt32_le(&valid_ks0_sc);
            println!("\n=== SC Summary: {} match(es) ===", total);
            if total == 0 {
                println!("FAIL: MT19937 with 32-bit seed does not match CT_0DA1 for any variant.");
            }
        }
        _ => {
            // joint (default): existing behavior, C→S+S→C joint key
            println!("=== Brute-Force: session 0x0032F714, quad ciphertext proto validation ===");
            println!("CT_1CD8 first bytes: {:02X} {:02X} {:02X}", CT_1CD8[0], CT_1CD8[1], CT_1CD8[2]);
            println!("CT_0794 first bytes: {:02X} {:02X} {:02X}", CT_0794[0], CT_0794[1], CT_0794[2]);
            println!("CT_102A first bytes: {:02X} {:02X} {:02X}", CT_102A[0], CT_102A[1], CT_102A[2]);
            println!("CT_061F ({} bytes), CT_0DA1 ({} bytes)", CT_061F.len(), CT_0DA1.len());

            let ct_firsts = [CT_1CD8[0], CT_0794[0], CT_102A[0]];
            let mut valid_ks0 = [false; 256];
            for k in 0..256usize {
                let kb = k as u8;
                valid_ks0[k] = ct_firsts.iter().all(|&ct| valid_proto_byte(kb ^ ct));
            }
            let valid_count = valid_ks0.iter().filter(|v| **v).count();
            println!("Valid K[0] values: {}/256 ({:.1}%)", valid_count, valid_count as f64 / 256.0 * 100.0);

            let mut total = 0usize;
            total += brute_mt64_be(&valid_ks0);
            total += brute_mt64_le(&valid_ks0);
            total += brute_mt32_be(&valid_ks0);
            total += brute_mt32_le(&valid_ks0);

            println!("\n=== Summary ===");
            if total == 0 {
                println!("FAIL: No u32 seed under Mt64-BE/LE or Mt32-BE/LE matched all ciphertext validators.");
                println!("This rules out MT19937 with a 32-bit seed as the joint session cipher for 0x0032F714.");
            } else {
                println!("{} total match(es) — review MATCH lines above.", total);
            }
        }
    }
}
