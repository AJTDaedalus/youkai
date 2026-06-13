# iZOD — Youkai Extended ZOD Format

ZOD ("Zenless Optimizer Data") is the community-standard JSON format for ZZZ inventory exports, accepted by [Zenless Optimizer](https://frzyc.github.io/zenless-optimizer/) and compatible tools. Youkai emits standard ZOD and extends it with an additive `talent` block on each character — hence **iZOD** (improved ZOD).

Importers that ignore unknown fields are unaffected. Importers that read `talent` get full skill-rank data not available from standard scanners.

---

## Top-level envelope

```json
{
  "format":     "GOOD",
  "version":    1,
  "source":     "Youkai",
  "characters": [ ... ],
  "discs":      [ ... ],
  "weapons":    [ ... ]
}
```

| Field        | Type   | Value     | Notes |
|--------------|--------|-----------|-------|
| `format`     | string | `"GOOD"`  | Fixed. Identifies the format family. |
| `version`    | int    | `1`       | Schema version. |
| `source`     | string | `"Youkai"`| Identifies the exporter. |
| `characters` | array  | `ZodAgent[]` | One entry per agent in the roster. |
| `discs`      | array  | `ZodDisc[]`  | All Drive Discs in inventory. |
| `weapons`    | array  | `ZodWEngine[]` | All W-Engines in inventory. |

---

## Drive Discs — `ZodDisc`

```json
{
  "setKey":      "ShockstarDisco",
  "slotKey":     "4",
  "level":       15,
  "rarity":      4,
  "mainStatKey": "CRIT Rate",
  "location":    "ZhuYuan",
  "lock":        true,
  "substats": [
    { "key": "ATK%",              "value": 9.0 },
    { "key": "CRIT DMG%",         "value": 9.4 },
    { "key": "Anomaly Proficiency","value": 18.0 },
    { "key": "PEN",               "value": 18.0 }
  ]
}
```

### Fields

| Field          | Type    | Notes |
|----------------|---------|-------|
| `setKey`       | string  | PascalCase disc set name. See [Set keys](#disc-set-keys). |
| `slotKey`      | string  | `"1"` through `"6"`. String, not integer. |
| `level`        | int     | 0–15. |
| `rarity`       | int     | `4` = S-rank, `3` = A-rank, `2` = B-rank. |
| `mainStatKey`  | string  | See [Main stat keys by slot](#main-stat-keys-by-slot). |
| `location`     | string  | Agent ZOD key if equipped; `""` if unequipped. |
| `lock`         | bool    | Whether the disc is locked in-game. |
| `substats`     | array   | 0–4 `ZodSubstat` objects. See [Substat keys](#substat-keys). |

### `ZodSubstat`

```json
{ "key": "CRIT DMG%", "value": 9.4 }
```

| Field   | Type   | Notes |
|---------|--------|-------|
| `key`   | string | Substat identifier. See [Substat keys](#substat-keys). |
| `value` | float  | Raw numeric value. Percentages are stored as `9.4`, not `0.094`. |

### Disc set keys

All disc set keys for ZZZ v1.4:

| Key | Display name |
|-----|-------------|
| `AstralVoice` | Astral Voice |
| `BranchBladeSong` | Branch & Blade Song |
| `BunnyInWonderland` | Bunny in Wonderland |
| `ChaosJazz` | Chaos Jazz |
| `ChaoticMetal` | Chaotic Metal |
| `DawnsBloom` | Dawn's Bloom |
| `FangedMetal` | Fanged Metal |
| `FreedomBlues` | Freedom Blues |
| `HormonePunk` | Hormone Punk |
| `InfernoMetal` | Inferno Metal |
| `KingOfTheSummit` | King of the Summit |
| `MoonlightLullaby` | Moonlight Lullaby |
| `NotesFromTheChained` | Notes from the Chained |
| `PhaethonsMelody` | Phaethon's Melody |
| `PolarMetal` | Polar Metal |
| `ProtoPunk` | Proto Punk |
| `PufferElectro` | Puffer Electro |
| `ShadowHarmony` | Shadow Harmony |
| `ShiningAria` | Shining Aria |
| `ShockstarDisco` | Shockstar Disco |
| `SoulRock` | Soul Rock |
| `SwingJazz` | Swing Jazz |
| `ThunderMetal` | Thunder Metal |
| `WhiteWaterBallad` | White Water Ballad |
| `WoodpeckerElectro` | Woodpecker Electro |
| `YunkuiTales` | Yunkui Tales |

### Slot keys

Slots are `"1"` through `"6"` (string values):

| Slot | Position |
|------|----------|
| `"1"` | Drive Disc 1 (HP main stat only) |
| `"2"` | Drive Disc 2 (ATK main stat only) |
| `"3"` | Drive Disc 3 (DEF main stat only) |
| `"4"` | Drive Disc 4 (variable main stat) |
| `"5"` | Drive Disc 5 (variable main stat) |
| `"6"` | Drive Disc 6 (variable main stat) |

### Main stat keys by slot

Slots 1–3 have fixed main stats. Slots 4–6 are variable.

| Slot | Valid `mainStatKey` values |
|------|---------------------------|
| `"1"` | `HP` |
| `"2"` | `ATK` |
| `"3"` | `DEF` |
| `"4"` | `HP`, `ATK`, `DEF`, `CRIT Rate`, `CRIT DMG`, `Anomaly Proficiency` |
| `"5"` | `HP`, `ATK`, `DEF`, `PEN`, `Electric DMG Bonus`, `Fire DMG Bonus`, `Ice DMG Bonus`, `Physical DMG Bonus`, `Ether DMG Bonus` |
| `"6"` | `HP`, `ATK`, `DEF`, `Anomaly Mastery`, `Impact`, `Energy Regen` |

### Substat keys

All possible substat keys (slots 1–6):

| Key | Stat |
|-----|------|
| `HP` | Flat HP |
| `ATK` | Flat ATK |
| `DEF` | Flat DEF |
| `HP%` | HP % |
| `ATK%` | ATK % |
| `DEF%` | DEF % |
| `PEN` | Flat Penetration |
| `CRIT Rate%` | CRIT Rate % |
| `CRIT DMG%` | CRIT DMG % |
| `Anomaly Proficiency` | Anomaly Proficiency (flat) |

Note: percentage substats use the `%` suffix in the key. Values are always raw numbers (`9.4` for 9.4% CRIT Rate, `18` for 18 Anomaly Proficiency).

---

## W-Engines — `ZodWEngine`

```json
{
  "key":        "SteelCushion",
  "level":      60,
  "ascension":  5,
  "refinement": 1,
  "location":   "ZhuYuan",
  "lock":       true
}
```

### Fields

| Field        | Type   | Notes |
|--------------|--------|-------|
| `key`        | string | PascalCase engine name. See [Engine keys](#engine-keys). |
| `level`      | int    | 1–60. |
| `ascension`  | int    | 0–5. Tracks the number of ascension breakthroughs. |
| `refinement` | int    | 1–5. |
| `location`   | string | Agent ZOD key if equipped; `""` if unequipped. |
| `lock`       | bool   | Whether the engine is locked in-game. |

### Engine keys

All W-Engine ZOD keys for ZZZ v1.4 (46 engines):

`BashfulDemon`, `BigCylinder`, `BoxCutter`, `BunnyBand`, `CannibalGrin`, `DeepSeaVisitor`, `DemaraBatteryMarkII`, `DoorOfLimitation`, `ElectroLipGloss`, `FinalCurtain`, `FusionCompiler`, `GildedBlossom`, `GrillOWisp`, `HailstormShrine`, `HellfireGears`, `Housekeeper`, `IdentityBase`, `IdentityInflection`, `KaboomTheCannon`, `LunarDecrescent`, `LunarNoviluna`, `LunarPleniluna`, `MagneticStormAlpha`, `MagneticStormBravo`, `MagneticStormCharlie`, `OriginalTransmorpher`, `Peacekeeper`, `PreciousFossilizedCore`, `RainforestGourmet`, `ReverbMarkI`, `ReverbMarkII`, `ReverbMarkIII`, `RoaringRide`, `SharpenedStinger`, `SliceOfTime`, `SpringEmbrace`, `StarlightEngine`, `SteamOven`, `TheBrimstone`, `TheRestrained`, `TheVault`, `TusksOfFury`, `VortexArrow`, `VortexHatchet`, `VortexRevolver`, `WeepingCradle`

---

## Agents (Characters) — `ZodAgent`

Standard ZOD defines the base four fields. Youkai adds `talent`.

```json
{
  "key":           "ZhuYuan",
  "level":         60,
  "constellation": 0,
  "ascension":     5,
  "talent": {
    "basic":   12,
    "dodge":    9,
    "assist":   9,
    "special": 12,
    "chain":   12,
    "core":     6
  }
}
```

### Fields

| Field           | Type       | Standard | Notes |
|-----------------|------------|----------|-------|
| `key`           | string     | Yes | PascalCase agent key. See [Agent keys](#agent-keys). |
| `level`         | int        | Yes | 1–60. |
| `constellation` | int        | Yes | Mindscape Cinema level, 0–6. |
| `ascension`     | int        | Yes | 0–6. Number of promotion breakthroughs completed. |
| `talent`        | ZodTalent  | **Youkai extension** | Six skill ranks. Omitted by standard scanners. |

### `ZodTalent` — Youkai extension

```json
{
  "basic":   12,
  "dodge":    9,
  "assist":   9,
  "special": 12,
  "chain":   12,
  "core":     6
}
```

| Field     | Type | Notes |
|-----------|------|-------|
| `basic`   | int  | Basic Attack rank. 1–12. |
| `dodge`   | int  | Dodge skill rank. 1–12. |
| `assist`  | int  | Assist rank. 1–12. |
| `special` | int  | Special Attack rank. 1–12. |
| `chain`   | int  | Chain Attack rank. 1–12. |
| `core`    | int  | Core Passive rank. 0–6 (maps to A/B/C/D/E/F nodes + inactive). |

`talent` is present on every agent entry Youkai scans. If an agent's agent page was not visited during the scan run, the entry may be absent — the exporter omits the field rather than emitting zeros.

### Agent keys

All agent ZOD keys for ZZZ v1.4 (54 agents):

`Alice`, `Anby`, `Anton`, `Aria`, `Astra`, `Banyue`, `Ben`, `Billy`, `Burnice`, `Caesar`, `Cissia`, `Corin`, `Dialyn`, `Ellen`, `Evelyn`, `Grace`, `Harumasa`, `Hugo`, `Jane`, `JuFufu`, `Koleda`, `Lighter`, `Lucia`, `Lucy`, `Lycaon`, `Manato`, `Miyabi`, `NangongYu`, `Nekomata`, `Nicole`, `OrphieMagus`, `PanYinhu`, `Piper`, `Promeia`, `Pulchra`, `Pyrois`, `Qingyi`, `Rina`, `Seed`, `Seth`, `Soldier0Anby`, `Soldier11`, `Soukaku`, `StarlightBilly`, `Sunna`, `Trigger`, `Vivian`, `Yanagi`, `YeShunguang`, `Yidhari`, `Yixuan`, `Yuzuha`, `Zhao`, `ZhuYuan`

---

## Key encoding

All string keys (set names, agent names, engine names) are encoded using `to_zod_key`:

1. Split on space, `_`, or `-` word boundaries.
2. Capitalize the first character of each word; leave the rest unchanged.
3. Strip all non-alphanumeric characters.

Examples:

| Raw display string | ZOD key |
|-------------------|---------|
| `Shockstar Disco` | `ShockstarDisco` |
| `Zhu Yuan` | `ZhuYuan` |
| `CRIT Rate` | `CRITRate` *(main stat — not a key type, shown for illustration)* |
| `Soldier 0 Anby` | `Soldier0Anby` |
| `Magnetic Storm α` | `MagneticStorm` *(non-ASCII stripped)* |

Agent and engine keys are derived from canonical short names in the Youkai data files (`data/zzz_1.4/agents.json`, `data/zzz_1.4/engines.json`). **Do not recompute keys from raw display strings** — use the data files as the authority.

---

## Equipped relationship

Gear is associated to agents via the `location` field, not via a list on the agent. To reconstruct loadouts downstream:

- For each disc/engine, if `location` is non-empty, that disc/engine is equipped on the agent matching that key.
- An agent entry with no matching disc `location` is unequipped.
- Multiple discs can share the same `location` (up to 6 discs per agent).
- At most one engine per agent.

Agents carry no gear list — reconstruct from `location` on the gear side.

---

## Backwards compatibility

`talent` is an additive extension. The `format` field remains `"GOOD"` and `version` remains `1`. Importers that skip unknown object fields will read the file correctly. Importers that explicitly read `talent` will get full skill-rank data.

No existing ZOD fields have been removed or renamed. Youkai will maintain this guarantee across patch updates; breaking schema changes (if ever needed) would increment `version`.

---

## Full example

```json
{
  "format": "GOOD",
  "version": 1,
  "source": "Youkai",
  "characters": [
    {
      "key": "ZhuYuan",
      "level": 60,
      "constellation": 0,
      "ascension": 5,
      "talent": {
        "basic": 12,
        "dodge": 9,
        "assist": 9,
        "special": 12,
        "chain": 12,
        "core": 6
      }
    }
  ],
  "discs": [
    {
      "setKey": "ShockstarDisco",
      "slotKey": "4",
      "level": 15,
      "rarity": 4,
      "mainStatKey": "CRIT Rate",
      "location": "ZhuYuan",
      "lock": true,
      "substats": [
        { "key": "ATK%",               "value": 9.0  },
        { "key": "CRIT DMG%",          "value": 9.4  },
        { "key": "Anomaly Proficiency", "value": 18.0 },
        { "key": "PEN",                "value": 18.0 }
      ]
    },
    {
      "setKey": "ShockstarDisco",
      "slotKey": "6",
      "level": 15,
      "rarity": 4,
      "mainStatKey": "Impact",
      "location": "",
      "lock": false,
      "substats": [
        { "key": "HP",     "value": 110.0 },
        { "key": "ATK",    "value": 19.0  },
        { "key": "CRIT Rate%", "value": 4.8 },
        { "key": "DEF%",   "value": 9.2   }
      ]
    }
  ],
  "weapons": [
    {
      "key": "SteelCushion",
      "level": 60,
      "ascension": 5,
      "refinement": 1,
      "location": "ZhuYuan",
      "lock": true
    }
  ]
}
```
