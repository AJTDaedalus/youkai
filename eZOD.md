# eZOD — Youkai Extended ZOD Format

ZOD ("Zenless Optimizer Data") is the community-standard JSON format for ZZZ inventory exports, accepted by [Zenless Optimizer](https://frzyc.github.io/zenless-optimizer/) and compatible tools. Youkai emits standard ZOD and extends it with an additive `talent` block on each character — hence **eZOD** (extended ZOD).

Importers that ignore unknown fields are unaffected. Importers that read `talent` get full skill-rank data not available from standard scanners.

---

## Top-level envelope

```json
{
  "format":     "eZOD",
  "version":    1,
  "source":     "Youkai",
  "characters": [ ... ],
  "discs":      [ ... ],
  "weapons":    [ ... ]
}
```

| Field        | Type   | Value     | Notes |
|--------------|--------|-----------|-------|
| `format`     | string | `"eZOD"`  | Fixed. Identifies the format family. |
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
  "mainStatKey": "crit_",
  "location":    "ZhuYuan",
  "lock":        true,
  "substats": [
    { "key": "atk_",      "value": 9.0 },
    { "key": "crit_dmg_", "value": 9.4 },
    { "key": "anomProf",  "value": 18.0 },
    { "key": "pen",       "value": 18.0 }
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
| `mainStatKey`  | string  | Stat key (AdeptiScanner/ZOD convention). See [Main stat keys by slot](#main-stat-keys-by-slot). |
| `location`     | string  | Agent ZOD key if equipped; `""` if unequipped. |
| `lock`         | bool    | Whether the disc is locked in-game. |
| `substats`     | array   | 0–4 `ZodSubstat` objects. See [Substat keys](#substat-keys). |

### `ZodSubstat`

```json
{ "key": "crit_dmg_", "value": 9.4 }
```

| Field   | Type   | Notes |
|---------|--------|-------|
| `key`   | string | Substat stat key. See [Substat keys](#substat-keys). May be `""` when the stat name could not be OCR'd (a known scan miss — the row still carries its `value`, and the field is emitted at low confidence). |
| `value` | float  | Raw numeric value. Percentages are stored as the magnitude (`9.4` for 9.4%, not `0.094`); flat stats store the raw integer value (e.g. `19` for flat ATK, `18` for flat PEN). |

> **Low-confidence flags on flat/% substats are expected and do not indicate wrong values.**
> The scanner OCRs a raw number (e.g. `3.2`) and must infer from context whether it is a flat
> or percentage stat. When both readings are plausible — e.g. DEF 10 (flat) vs DEF 3.2% —
> OCR confidence is inherently lower than for unambiguous fields. Spot-checks on ~1 000
> flagged substats confirm the values are correct; the flags reflect genuine numerical
> ambiguity, not data corruption.

### Disc set keys

All disc set keys for ZZZ v1.4+ (30 sets):

| Key | Display name |
|-----|-------------|
| `AstralVoice` | Astral Voice |
| `BranchBladeSong` | Branch & Blade Song |
| `BunnyInWonderland` | Bunny in Wonderland |
| `ChaosJazz` | Chaos Jazz |
| `ChaoticMetal` | Chaotic Metal |
| `DawnsBloom` | Dawn's Bloom |
| `FangedMetal` | Fanged Metal |
| `FeatheredFate` | Feathered Fate |
| `FreedomBlues` | Freedom Blues |
| `HormonePunk` | Hormone Punk |
| `InfernoMetal` | Inferno Metal |
| `KingOfTheSummit` | King of the Summit |
| `MoonlightLullaby` | Moonlight Lullaby |
| `NotesFromTheChained` | Notes From the Chained |
| `PhaethonsMelody` | Phaethon's Melody |
| `PolarMetal` | Polar Metal |
| `ProtoPunk` | Proto Punk |
| `PufferElectro` | Puffer Electro |
| `ShadowHarmony` | Shadow Harmony |
| `ShiningAria` | Shining Aria |
| `ShockstarDisco` | Shockstar Disco |
| `SoulRock` | Soul Rock |
| `SwingJazz` | Swing Jazz |
| `TheSkyAblaze` | The Sky Ablaze |
| `ThornedRose` | Thorned Rose |
| `ThunderMetal` | Thunder Metal |
| `WhiteWaterBallad` | White Water Ballad |
| `WoodpeckerElectro` | Woodpecker Electro |
| `WutheringSalon` | Wuthering Salon |
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

Slots 1–3 have fixed main stats. Slots 4–6 are variable. Keys follow the
AdeptiScanner/ZOD convention: lowercase, with a trailing `_` marking a
percentage stat. The same flat-vs-percent display text means different things by
slot (slot-1 `HP` is flat → `hp`; slot-4 `HP` is percent → `hp_`).

| Slot | In-game main stat | `mainStatKey` |
|------|-------------------|---------------|
| `"1"` | HP (flat) | `hp` |
| `"2"` | ATK (flat) | `atk` |
| `"3"` | DEF (flat) | `def` |
| `"4"` | HP% / ATK% / DEF% / CRIT Rate / CRIT DMG / Anomaly Proficiency | `hp_` / `atk_` / `def_` / `crit_` / `crit_dmg_` / `anomProf` |
| `"5"` | HP% / ATK% / DEF% / PEN% / Electric/Fire/Ice/Physical/Ether DMG Bonus | `hp_` / `atk_` / `def_` / `pen_` / `electric_dmg_` / `fire_dmg_` / `ice_dmg_` / `physical_dmg_` / `ether_dmg_` |
| `"6"` | HP% / ATK% / DEF% / Anomaly Mastery / Impact / Energy Regen | `hp_` / `atk_` / `def_` / `anomMas_` / `impact_` / `enerRegen_` |

### Substat keys

All possible substat keys (slots 1–6). Same lowercase/trailing-`_` convention:

| Key | Stat |
|-----|------|
| `hp` | Flat HP |
| `atk` | Flat ATK |
| `def` | Flat DEF |
| `hp_` | HP % |
| `atk_` | ATK % |
| `def_` | DEF % |
| `pen` | Flat Penetration |
| `crit_` | CRIT Rate % |
| `crit_dmg_` | CRIT DMG % |
| `anomProf` | Anomaly Proficiency (flat) |

`value` is always the raw magnitude: `9.4` for 9.4% CRIT DMG (`crit_dmg_`), `18`
for 18 Anomaly Proficiency (`anomProf`), `19` for flat ATK (`atk`).

> **Note:** these stat keys are **not** produced by `to_zod_key`. They come from
> `data/zzz_1.4/stats.json` (sourced from AdeptiScanner-ZZZ) and match the
> standard ZOD/optimizer convention. Only set / agent / engine keys use
> `to_zod_key` (see [Key encoding](#key-encoding)).

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

All W-Engine ZOD keys for ZZZ v1.4+ (99 engines):

`AngelInTheShell`, `BashfulDemon`, `BellicoseBlaze`, `BigCylinder`, `BlazingLaurel`, `BloodmarrowCoffer`, `BoisterousEchoes`, `BoxCutter`, `BunnyBand`, `CannonRotor`, `CattyLuck`, `CauldronOfClarity`, `ChiefSidekick`, `CinderCobalt`, `CloudcleaveRadiance`, `CordisGermina`, `CrimsonThirst`, `DeepSeaVisitor`, `DemaraBatteryMarkII`, `DreamlitHearth`, `DrillRigRedAxis`, `ElectroLipGloss`, `ElegantVanity`, `FlamemakerShaker`, `FlightOfFancy`, `FrostfallSickle`, `FusionCompiler`, `GildedBlossom`, `GrillOWisp`, `HailstormShrine`, `HalfSugarBunny`, `HeartstringNocturne`, `HellfireGears`, `Housekeeper`, `IceJadeTeapot`, `IdentityBase`, `IdentityInflection`, `JoyauDore`, `KaboomTheCannon`, `KnightsExtolment`, `KrakensCradle`, `LunarDecrescent`, `LunarNoviluna`, `LunarPleniluna`, `LunarSemiluna`, `MagneticStormAlpha`, `MagneticStormBravo`, `MagneticStormCharlie`, `MarcatoDesire`, `Metanukimorphosis`, `MyriadEclipse`, `NeonFantasies`, `OdeOfResurrectedWings`, `OriginalTransmorpher`, `PeacekeeperSpecialized`, `PracticedPerfection`, `PreciousFossilizedCore`, `PuzzleSphere`, `QingmingBirdcage`, `RadiowaveJourney`, `RainforestGourmet`, `ReelProjector`, `ReverbMarkI`, `ReverbMarkII`, `ReverbMarkIII`, `RiotSuppressorMarkVI`, `RoaringFurnace`, `RoaringRide`, `SerpentineSeeker`, `SeveredInnocence`, `SharpenedStinger`, `SixShooter`, `SliceOfTime`, `SolExuvia`, `SpectralGaze`, `SpringEmbrace`, `StarlightEngine`, `StarlightEngineReplica`, `StarlightRiderFaceplate`, `SteamOven`, `SteelCushion`, `StreetSuperstar`, `TheBrimstone`, `TheRestrained`, `TheSimmeringPot`, `TheVault`, `Thoughtbop`, `Timeweaver`, `TremorTrigramVessel`, `TusksOfFury`, `UnfetteredGameBall`, `VortexArrow`, `VortexHatchet`, `VortexRevolver`, `WeepingCradle`, `WeepingGemini`, `WrathfulVajra`, `YesterdayCalls`, `ZanshinHerbCase`

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
| `core`    | int  | Core Skill rank. `0` = none/not unlocked; `1`–`6` map to in-game ranks **A–F**. |

> **Downstream mapping notes (eZOD → optimizer build):**
> - `talent.core` is the **Core Skill A–F rank**, not a numeric (1–12) attack
>   level. ZZZ has no separate numeric core level — the A–F rank *is* the core
>   stat. Map it to your "core skill level / passive tier" field, and remember
>   the offset: eZOD `0`=none, `1`=A … `6`=F (so an optimizer that encodes A–F as
>   `0`–`5` should subtract 1 and treat eZOD `0` as null/locked).
> - `assist` is the Assist skill rank (1–12). Optimizers that don't model assist
>   can drop it; the other five (`basic`, `dodge`, `special`, `chain`) are the
>   numeric 1–12 skill levels.

`talent` is present on every agent entry Youkai scans. If an agent's agent page was not visited during the scan run, the entry may be absent — the exporter omits the field rather than emitting zeros.

### Agent keys

All agent ZOD keys for ZZZ v1.4+ (59 agents):

`Alice`, `Anby`, `Anton`, `Aria`, `Astra`, `Banyue`, `Ben`, `Billy`, `Burnice`, `Caesar`, `Cissia`, `Corin`, `Dialyn`, `Ellen`, `Evelyn`, `Grace`, `Harumasa`, `Hugo`, `Jane`, `JuFufu`, `Koleda`, `Lighter`, `Lucia`, `Lucy`, `Lycaon`, `Manato`, `Miyabi`, `NangongYu`, `Nekomata`, `Nicole`, `Norma`, `OrphieMagus`, `PanYinhu`, `Piper`, `Promeia`, `Pulchra`, `Pyrois`, `Qingyi`, `Remielle`, `Rina`, `Roxy`, `Seed`, `Seth`, `Sigrid`, `Soldier0Anby`, `Soldier11`, `Soukaku`, `StarlightBilly`, `Sunna`, `Trigger`, `Velina`, `Vivian`, `Yanagi`, `YeShunguang`, `Yidhari`, `Yixuan`, `Yuzuha`, `Zhao`, `ZhuYuan`

---

## Key encoding

**Set, agent, and engine** keys are encoded using `to_zod_key`. (Stat keys are
**not** — they come from `data/zzz_1.4/stats.json`; see [Substat keys](#substat-keys).)

`to_zod_key` rules:

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

> **Keeping the lists honest:** the disc-set, engine and agent enumerations above are
> copies of `data/zzz_1.4/*.json` as of the last content sync, kept for readability.
> Regenerate all three from the data files whenever content is added — a partial update
> leaves the doc advertising keys the scanner never emits.
>
> **Downstream note:** these keys are Youkai-canonical. They follow the ZOD
> PascalCase convention but are **not** guaranteed byte-identical to any other
> tool's character/engine keys. To build a `key → display name` map, read
> `data/zzz_1.4/agents.json` and `engines.json` directly (each key lists its
> accepted display names) — not the Genshin optimizer (different game) or an
> assumed alias table.

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

`talent` is an additive extension. The `format` field remains `"eZOD"` and `version` remains `1`. Importers that skip unknown object fields will read the file correctly. Importers that explicitly read `talent` will get full skill-rank data.

No existing ZOD fields have been removed or renamed. Youkai will maintain this guarantee across patch updates; breaking schema changes (if ever needed) would increment `version`.

---

## Full example

```json
{
  "format": "eZOD",
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
      "mainStatKey": "crit_",
      "location": "ZhuYuan",
      "lock": true,
      "substats": [
        { "key": "atk_",      "value": 9.0  },
        { "key": "crit_dmg_", "value": 9.4  },
        { "key": "anomProf",  "value": 18.0 },
        { "key": "pen",       "value": 18.0 }
      ]
    },
    {
      "setKey": "ShockstarDisco",
      "slotKey": "6",
      "level": 15,
      "rarity": 4,
      "mainStatKey": "impact_",
      "location": "",
      "lock": false,
      "substats": [
        { "key": "hp",    "value": 110.0 },
        { "key": "atk",   "value": 19.0  },
        { "key": "crit_", "value": 4.8   },
        { "key": "def_",  "value": 9.2   }
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
