use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ZodSubstat {
    pub key: String,
    pub value: f32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ZodDisc {
    pub set_key: String,
    pub slot_key: String, // String "1" through "6"
    pub level: u32,
    pub rarity: u32, // Rarity (e.g. 4 for S-rank, 3 for A-rank)
    pub main_stat_key: String,
    pub location: String, // Equipped character key (empty if unequipped)
    pub lock: bool,
    pub substats: Vec<ZodSubstat>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ZodWEngine {
    pub key: String,
    pub level: u32,
    pub ascension: u32,
    pub refinement: u32,
    pub location: String, // Equipped character key (empty if unequipped)
    pub lock: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ZodAgent {
    pub key: String,
    pub level: u32,
    pub constellation: u32, // Mindscape Cinema level (0-6)
    pub ascension: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ZodExport {
    pub format: String, // "GOOD"
    pub version: u32,   // 1
    pub source: String, // "Youkai"
    pub characters: Vec<ZodAgent>,
    pub discs: Vec<ZodDisc>,
    pub weapons: Vec<ZodWEngine>,
}

/// Normalizes arbitrary game strings into camelCase or PascalCase alphanumeric keys
/// required by community build optimizers (e.g. "Shockstar Disc" -> "ShockstarDisc")
pub fn to_zod_key(value: &str) -> String {
    let mut result = String::new();
    let mut capitalize_next = true;

    for c in value.chars() {
        if c.is_ascii_alphanumeric() {
            if capitalize_next {
                result.extend(c.to_uppercase());
                capitalize_next = false;
            } else {
                result.push(c);
            }
        } else if c == ' ' || c == '_' || c == '-' {
            capitalize_next = true;
        }
    }

    result
}
