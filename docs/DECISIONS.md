# DECISIONS — Youkai

Append-only. Each decision: context, options, choice, rationale.

---

## D1 — Validate-then-rewrite, not rewrite-then-hope (2026-05-23)

**Context**: Three plausible paths to start: (a) immediately rewrite `HandshakePacket::parse` to the 20-byte format and ship a cipher binding, (b) build an isolated probe binary that proves the seed identity offline before touching production code, (c) brute-force the seed first via `brute.rs`.

**Choice**: (b) — Phase 1 probe binary, gated decision before Phase 2 production rewrites.

**Rationale**: The previous agent shipped a handshake parser based on an unverified spec from the README and an unrelated cipher binding. Repeating that mistake — rewriting based on the new 20-byte spec without verifying that the token actually seeds the cipher — risks a second wasted iteration. The probe is one file, one binary, ~90 minutes of work, and either proves the hypothesis or generates a precise failure signature. (a) skips verification and risks burning another iteration. (c) is the slowest and weakest signal — brute-force on uncertain plaintext returns ambiguous failures (was the plaintext wrong, the cipher wrong, the encoding wrong?).

**Rejected**: Rewriting the handshake parser before P1 — risk of repeating the prior agent's error of trusting a spec.

---

## D2 — Seed orientations to test in P1 (2026-05-23)

**Context**: The token at offset 8–11 of the 20-byte handshake is the strongest seed candidate, but the bytes can be interpreted multiple ways. We must enumerate exhaustively in P1 so a single negative result actually rules MT19937 out.

**Choice**: Try all of the following, in order, in `decrypt_probe.rs`:

For session `0x0042CEA1`, raw token bytes are `EA 5F 26 2D`.

1. `LE u32` → `0x2D265FEA` as `u64` seed to `Mt64`.
2. `BE u32` → `0xEA5F262D` as `u64` seed to `Mt64`.
3. `LE u32` zero-extended to u64 → already #1.
4. `BE u32` zero-extended to u64 → already #2.
5. `LE u32` XOR `0x499602D2` → mix the constant in.
6. `BE u32` XOR `0x499602D2`.
7. `LE u32` concatenated with `0x499602D2` LE → as `u64` seed.
8. `LE u32` concatenated with `0x499602D2` BE → as `u64` seed.
9. Same eight variants but using 32-bit `rand_mt::Mt`, with keystream bytes packed BE then LE.

The probe also tries body offset 4 (for the `10 00 00 00` prefix anomaly) for each orientation.

**Rationale**: 16 orientations is small enough to enumerate in one binary, large enough to credibly say "MT19937 from a single 32-bit seed is not the cipher" on a clean failure. Mixing in the `0x499602D2` constant tests the hypothesis that it's not just a protocol version but a nonce/key component.

**Rejected**: Hashing the token via SHA-256/MD5 first — neither is hinted at by the handshake structure; defer to Phase 4 if needed.

---

## D3 — MT19937 variants (2026-05-23)

**Context**: `rand_mt` exposes both `Mt` (32-bit MT19937) and `Mt64` (MT19937-64). The current `GenericMtCipher` uses `Mt64::new(seed as u64)` with BE byte packing. If the actual game uses 32-bit MT19937 or a Boost-style variant with different initialization, our brute-force and our cipher both miss.

**Choice**: P1 probe (T1.5) tries `Mt64` first because that's the current `GenericMtCipher` and the brute.rs's existing assumption. T1.6 falls back to `Mt` (32-bit). Boost variants are deferred to Phase 4 if both fail.

**Rationale**: `Mt64` is the closest to the prior agent's assumed model. Trying `Mt64` first lets us inherit the existing cipher impl if it works. The 32-bit MT19937 is the more common "MT19937" referenced in game-RE literature; if `Mt64` fails, `Mt` is the strongest next candidate.

**Rejected**: Implementing every Boost MT initialization variant upfront — too much speculative code before the simple cases are tested.

---

## D4 — Per-conv state instead of global state (2026-05-23)

**Context**: `Monitor` today holds a single `Reassembler` and a single `cipher`. Four concurrent ZZZ sessions exist in the dataset, and any real capture will see at least two streams (client→server and server→client).

**Choice**: `HashMap<u32, Reassembler>` and `HashMap<u32, Box<dyn YoukaiCipher>>` keyed by `conv`.

**Rationale**: The README explicitly warns about cross-conv fragment interleaving (packet_research/README.md §2). The cipher must also be per-conv because every session negotiates its own seed. A global cipher would XOR session B's bytes with session A's keystream.

**Rejected**: Per-conv-per-direction (i.e., keying by `(conv, direction)`). KCP `conv` values appear unique enough across directions in the dataset; if direction matters, the keying scheme can be tightened later without changing the trait surface.

**Rejected**: A single `Reassembler` with a `(conv, sn)` composite key — same effect, but a `HashMap<conv, Reassembler>` is a more natural unit of cleanup (drop the entry when a session ends) and matches the cipher map's shape.

---

## D5 — Decrypt on reassembled body, not on each fragment (2026-05-23)

**Context**: Current `monitor.rs:196` decrypts each KCP segment payload independently. An MT keystream advances byte-by-byte across the full body; if the body spans two fragments, each fragment decrypted with a fresh-from-position-0 keystream would corrupt both.

**Choice**: Decrypt after reassembly, on the full `complete_message`.

**Rationale**: The cipher is stream-based per session, not per-fragment. The current code happens not to misbehave because `PassThroughCipher` is bound — but the moment a real cipher binds, it would mangle multi-fragment messages.

**Open question**: If a single body exceeds MTU and spans multiple fragments, this is the only correct option. If a body fits in one fragment, both approaches are equivalent. Decrypting on reassembled is the safer default.

---

## D6 — Keep `gi.json` and `GameSniffer` untouched for now (2026-05-23)

**Context**: `monitor.rs:75` loads Genshin keys and constructs a `GameSniffer`. None of the dataset is Genshin traffic, but the code path must not break for users who actually use Youkai for Genshin captures.

**Choice**: Leave the Genshin pipeline alone in this plan. Bind `PassThroughCipher` as the default for unknown convs (Genshin convs included), and route ZZZ-recognized convs through the new cipher map. Do not feed decrypted ZZZ bodies into `GameSniffer` — write a thin ZZZ frame parser in `monitor.rs` instead.

**Rationale**: `auto_artifactarium::GameSniffer` is built around Genshin's framing; ZZZ's frame layout (start magic + CmdId + head_len + body_len + body + end magic) is documented and small enough to parse directly. Mixing the two pipelines invites cross-contamination bugs. If the formats turn out to overlap perfectly, we can collapse them in a follow-up.

---

## D7 — Stop at Phase 1 failure; do not proceed to Phase 2 (2026-05-23)

**Context**: It is tempting to also rewrite the handshake parser even if Phase 1 fails to recover a seed, because the parser is obviously broken and the new 20-byte format is empirically verified.

**Choice**: Hard stop at T1.7 if P1 fails. Phase 2/3 are explicitly gated.

**Rationale**: The handshake parser rewrite is correct in isolation, but its only consumer is the cipher binding. Without a known cipher recipe, binding `GenericMtCipher` from the token achieves nothing — the cipher map will be populated, but decrypt output will still be garbage. Better to leave the parser broken (visibly so) than to land a "fix" that looks complete but produces wrong output. Phase 4's brute-force, or a different cipher entirely, is the real next step.

**Exception**: T2.3 (per-conv `Reassembler`) is a pure bugfix independent of the cipher. If P1 fails, we may pull T2.3 forward as a standalone improvement under a separate plan — but not under this DESIGN.

---

## D8 — v1 plan abandoned; pivot to auto-artifactarium-style attack (2026-05-23)

**Context**: Phase 1's u32-seed brute-force exhausted with zero matches. `HANDOFF_decryption_v2.md` concluded the cipher seed must be a u64 from RSA key exchange and is unrecoverable passively. That conclusion was wrong: `hashblen/auto-artifactarium` recovers Genshin session keys passively via a weak-RNG attack on `client_rand_key` (C# `System.Random` seeded with `Environment.TickCount`). The same family of code powers `IceDynamix/reliquary` (HSR). miHoYo almost certainly reused it in ZZZ.

**Choice**: Adopt the auto-artifactarium attack model for ZZZ. See `DESIGN_decryption_v2.md` + `TASKS_decryption_v2.md`. v1 design and tasks files are superseded but kept on disk for history.

**Rationale**: This is the only known passive attack on the miHoYo cipher family, it is published and verified to work on two sibling games, and it requires only the version-specific initial xorpad (extractable from the client binary) plus packet timestamps. The user explicitly opted to self-extract the v2.8 initial xorpad rather than ask the reversedrooms community.

**Ruled out**: Path A (extract both client AND server RSA private keys — server key not in binary, infeasible). Path C (emulator capture — no real inventory data). Path D (community ask — declined by user). Path B (known-plaintext) retained only as fallback if Phase 3 RNG model is wrong.

**Risk**: If ZZZ migrated from C# `System.Random` to a stronger RNG between Genshin and v2.8, the seed search may not collapse and we'll need Path B. DESIGN §5c enumerates the fallback RNG candidates to try before escalating.

---

## D9 — v2 binary-extraction path replaced by known-plaintext attack (2026-05-24)

**Context**: v2 §5a assumed the `ec2b` blob would be findable in the ZZZ client binary by greping for magic bytes. The previous Sonnet session verified this assumption is wrong for v2.8: no `Ec2b` / `ec 2b 00 00` magic anywhere in the launcher, IL2CPP DLLs, Unity runtime, or asset files. `global-metadata.dat` is MHY-encrypted and not greppable in plaintext.

**Five options evaluated** (see `HANDOFF_decryption_v3.md` §2):

- **O1 — published community xorpad**: declined as primary; no open-source ZZZ tool ships the real (non-emulator) v2.8 xorpad. Reserved as last resort.
- **O2 — runtime memory dump**: **ruled out** by `DESIGN_decryption_v2.md` §4 non-goal forbidding process memory reading.
- **O3 — known-plaintext on token exchange**: **chosen as primary**. The per-field XOR-obfuscation constants in `nap_generated.zig` force miHoYo's encoder to emit fields on the wire even when the real value is zero, because the wire value (= real ⊕ obf_constant) is non-zero. This makes most CsReq/ScRsp bytes predictable from the schema alone, with three opaque gaps (`client_rand_key`, `sign`, `server_rand_key`). Union of CsReq+ScRsp coverage should reach ≥60% of pad[0..600] and is likely to cover the `server_rand_key` region.
- **O4 — MHY metadata decryption**: viable parallel investigative track, time-boxed to 2 hours. If a Sonnet worker can port the Il2CppDumper-style decryption routine and recover plaintext `global-metadata.dat`, the `Ec2b` magic should be findable there. Heavy lift; not on critical path.
- **O5 — binary scan with O3 fingerprint as oracle**: chosen as hybrid finisher if O3 coverage doesn't reach `server_rand_key`. A 32-byte high-confidence fingerprint from O3 gives <2^-64 false-positive rate against any aligned candidate 4096-byte region in `GameAssembly.dll`.

**Choice**: O3 primary, O5 hybrid finisher, O4 parallel time-boxed, O1 last resort, O2 ruled out.

**Rationale**: O3 alone is much stronger than the handoff treated it as, once the proto3-skip vs miHoYo-XOR-obfuscation interaction is understood. The hybrid O3+O5 sequence requires no community artifacts, no DLL injection, no memory reading, and stays inside the user's stated non-goals. O4 is the cleanest path if it lands but has unknown effort.

**Risk**: OQ-v3-2 — if `server_rand_key` turns out to be RSA-encrypted (256 bytes) rather than plaintext u64 (8 bytes), the passive attack becomes infeasible regardless of which option lands the initial xorpad. Detection point is T2'.2; if it fires, escalate immediately.

---

## D10 — Capture tool format kept as-is (2026-05-24)

**Context**: Existing capture format = one raw Ethernet frame per file with timestamp-derived filename. Produces 20,000+ small files per session. Wireshark/pcap would consolidate to one file.

**Choice**: Keep existing format. The probe binaries already parse it. Switching mid-investigation invites breakage in parsers that have been working.

**Revisit when**: post-Phase-3 cleanup, if file-count becomes a UX problem for the user.

---

## D11 — Adopt dispatch + client-RSA path for ec2b; gate on the session-key crux (2026-06-01)

**Context**: v2/v3 stalled trying to extract the ec2b initial key from `GameAssembly.dll` (D9 — not greppable, MHY-encrypted). External advice (and partially-written scripts already on disk: `fetch_dispatch.py`, `capture_dispatch.py`, `try_rsa_decrypt.py`) points to a cleaner source: the ec2b/region key is delivered in the **dispatch HTTP response** and decryptable with an RSA key embedded in the client and published in `thexeondev/ZZZKeys` (rsa_ver 1/2/3, game ≤1.0.0).

**Choice**: Adopt the dispatch + client-RSA path as the primary route to the ec2b/initial xorpad, replacing binary extraction. See `DESIGN_decryption_v4.md` + `TASKS_decryption_v4.md`. v3 hybrid (O3 known-plaintext + O5 binary fingerprint) demoted to fallback.

**Rationale**: Bypasses the D9 blocker entirely with no client modification and no memory reading (keeps N1/N2). The ec2b arrives on the wire; we only need the (published) client key to decrypt it.

**Hard gate — the crux (OQ-v4-1)**: ec2b alone does NOT guarantee game-state decryption. The session key = `client_seed ⊕ server_seed`. With only the client private key a passive observer can recover `server_seed` (server_rand_key is RSA'd to the *client* key) but NOT `client_seed` (client_rand_key is RSA'd to the *server* key we lack). Passive recovery is viable only if the client seed is weak-RNG/brute-forceable (C1), the seeds are plaintext after ec2b decryption (C2), or the key derives single-sided (C3). If it is strong two-sided (C0), **passive recovery is infeasible with the client key alone and we STOP** (DESIGN §3, Gate A). This is resolved FIRST, from emulator source, before any tooling.

**Safety posture (user asked to stay very safe)**: Strict preference order — passive UDP capture and **fetch-dispatch** (independent script hitting the public endpoint, never touching the live game) are low-risk and primary. **Live-traffic HTTPS interception (proxy + custom CA) is high-risk** (anti-cheat/pinning) and is last-resort, observation-only, user-confirmed. **Forbidden**: client/binary patching, memory editing, private-server login, traffic modification (N1–N4). Keys/pads stay out of git (S4).

**Ruled out / demoted**: binary ec2b extraction (D9) → fallback only; any active interception as primary → no.

**Risk**: rsa_ver may have rotated past the ZZZKeys-published key 3 by v2.8 (OQ-v4-2, Gate B). If so, the published key won't decrypt dispatch and client extraction is N1/N2-forbidden → escalate to user.

---

## D12 — Gate A resolved from emulator source: case is C0/C1; dispatch path alone insufficient (2026-06-01)

**Context**: Phase 0 read yixuan-rs (cloned read-only) to settle the crux before building tooling. Full model in `docs/RESEARCH_zzz_dispatch_model.md` with file:line citations.

**Findings (decisive code = `gate-server/src/encryption.rs:22-57`)**:
- `session_seed = client_seed ^ server_seed` (line 56) — genuinely two-sided (rules out C3).
- `client_rand_key` (CsReq) is RSA-encrypted to the **server** public key; server decrypts with its private key (line 34). We lack the server key → **client_seed is opaque to a passive observer** (rules out C2: it's a 128-byte RSA blob, not plaintext).
- `server_rand_key` (ScRsp) is RSA-encrypted to the **client** public key (line 46-49); the client — and we, with the ZZZKeys client private key — decrypt it → **server_seed recoverable** (8-byte u64 LE).
- `server_seed` is a CSPRNG `thread_rng().next_u64()` (line 44) — not predictable, but we don't need to predict it; we decrypt it.
- Dispatch `content` model (multi-block PKCS1 RSA → JSON → `client_secret_key` = ec2b) and the ec2b→Mt64 recipe are confirmed (rsa.rs, ec/mod.rs, config.rs). Orientation: **initial pad LE, session pad BE** (config.rs:42 vs handlers.rs:229-231).

**Choice**: Proceed with the dispatch+RSA path, but treat it as **necessary-not-sufficient**. Add **Phase 3.5**: recover server_seed via RSA, then **brute client_seed** under a weak-RNG hypothesis (auto-artifactarium / D8) validated by the proto3 oracle. The brute is now tractable because server_seed is fixed — we search the client RNG state, not the full 2^64 session seed (this is also why the prior blind u32 session-seed brute failed, D8/LOG 2026-05-23).

**Gate A verdict**: **C0/C1, not C2/C3.** Cannot distinguish C0 from C1 from the emulator (it has no client code). Resolve empirically at **Gate E**: a proto3-oracle hit during the client_seed brute ⇒ C1 (solved); a generous time/RNG window exhausted with no hit ⇒ likely C0 ⇒ passive recovery infeasible ⇒ STOP (do not pursue N1–N3).

**Net effect on the advisor's advice**: "extract RSA key + sniff dispatch" is correct and unblocks ec2b + server_seed, but by itself does NOT yield game state — it must be combined with the weak-client-RNG brute. The two paths are complementary.

---

## D13 — Dispatch wall broken: retcode 70 root-caused, Gate B PASSED, blocker narrowed to dispatch_seed (2026-06-01, Opus)

**Context**: Phase 2a returned `{"retcode":70}` for every query_dispatch variant and HTTP 599 on the
query_gateway fallback (LOG, Sonnet 2026-06-01). Escalated to Opus. Resolved by static RE (the client's
own `[GlobalDispatch]` log line + binary/metadata) plus 3 live read-only GETs (S1/S3).

**Findings (all live-verified against the official server):**
1. **retcode 70 = malformed `version` param.** The client sends the FULL build string
   `version=OSPRODWin2.8.0` (+ `language=1`, `platform=3`); our script sent bare `version=2.8.0&t=0`.
   Bare `2.8.0` matches no region → retcode 70. Corrected request → `retcode:0` + full `region_list`.
   ⇒ **OQ "is the host wrong?" = NO.** `globaldp-prod-os01.zenlesszonezero.com` is correct (it is the
   region-picker host only).
2. **query_gateway is on a per-region host**, not the dispatch host: prod_gf_us →
   `https://prod-gf-us.zenlesszonezero.com/query_gateway`. The old "hit the dispatch host directly"
   fallback was the source of HTTP 599.
3. **★ GATE B = PASS (OQ-v4-2 resolved):** the ZZZKeys **rsa_ver-3** client private key (modulus
   `rkQoCtGS…`) cleanly RSA-decrypts the live v2.8 gateway `content`; the server also accepts
   `rsa_ver=3` (returned 75, not the rsa_ver error 74). **The key has NOT rotated — no STOP, no
   forbidden client extraction needed.** This directly answers the user's standing question: *yes, the
   published ZZZKeys key is still in use at v2.8.*
4. **Remaining blocker (narrowed):** query_gateway needs the correct **`dispatch_seed`** — a
   per-version CONSTANT (8 bytes/16 hex), checked as `resource_version.dispatch_seed != param.seed`
   (yixuan handlers.rs:136). Empty/wrong seed → encrypted `{"retcode":75}`. It is NOT in the game logs
   and NOT a plaintext literal in `global-metadata.dat` (v2.8 encrypts IL2CPP string literals; the only
   16-hex matches are .NET PublicKeyTokens). Because it is a constant, recovering it ONCE permanently
   unblocks all offline work.

**Choice**: Treat Phase 2 (ec2b/initial xorpad) as unblocked **except** for the `dispatch_seed` value.
Three options to obtain it, in safety order: (a) **pivot first** to Phase 3.5/Gate E (brute client_seed
— the real make-or-break; doesn't need ec2b to start); (b) **IL2CPP dump** with metadata
string-literal decryption (static, heavier); (c) **one MITM observation** of a single real
query_gateway request to read `seed=` (decisive/minimal, but the S5 high-risk HTTPS-intercept path →
explicit user OK required). **Decision deferred to user** (recorded as the open question below).

**Net effect**: The dispatch+client-RSA route is proven viable to the last constant. The strategic
crux is unchanged — Gate E (C0 vs C1) still decides whether passive recovery is possible at all (D12).

**Updated artifacts**: `packet_research/fetch_dispatch.py` (correct params + per-region URL +
`DISPATCH_SEED` slot), `LOG_decryption_v4.md` (full session), `state/v2.8/*.json` (raw evidence).

---

## D14 — Static C0/C1 determination blocked by MHY metadata encryption; evidence converges on C0 → recommend STOP for passive game-state recovery (2026-06-01, Opus; user-approved static-only dump)

**Context**: Per D13, the make-or-break is Gate E (C0 vs C1 — is `client_rand_key` weak/brute-forceable?).
User chose to resolve C0/C1 first, and authorized a **static-only** IL2CPP dump (no game launch, no memory
read, read-only — runtime/memory dumping explicitly OFF per N2 + safety rules).

**Static dump = BLOCKED by miHoYo metadata protection:**
- `global-metadata.dat` header = `4D 48 59 00` ("MHY\0"), not the standard il2cpp magic `0xFAB11BAF`.
- IL2CPP **symbol/name + string tables are encrypted**: 0 hits for any app symbol (`PlayerGetTokenCsReq`,
  `SecurityModule`, `PlayerLoginCsReq`, `*RandKey*`, `Mt19937`, …). Only .NET BCL *data* strings survive.
  This is also why `dispatch_seed` (D13) wasn't a plaintext literal.
- Breaking it statically needs the MHY metadata decryptor reversed out of GameAssembly.dll (487 MB stripped
  PE) — an IDA/Ghidra-class project; this env has only objdump/nm (no IDA/Ghidra/radare, no dotnet/mono).
  Blind native-function location (encrypted string xrefs, no symbols) is infeasible by hand.
- The only "easy" alternative (runtime/memory metadata dump) is **forbidden** (N2, anti-cheat/account risk).

**Evidence on C0 vs C1 (all from SAFE sources) — converges on C0 (strong RNG):**
1. Binary links proper CSPRNGs (`BCryptGenRandom`, `RAND_bytes`, `ctr_drbg`/DRBG entropy pools); **no**
   `System.Random` / `UnityEngine.Random` / `xorshift` / `mt19937` as a rand-key source. (suggestive: those
   CSPRNGs are also linked for TLS)
2. Protocol design: the key is `client_seed ^ server_seed` with `client_rand_key` RSA-encrypted to the
   **server** key — a contributory two-sided exchange whose entire purpose is defeated if the client seed is
   predictable. A competent implementer pairs this with a CSPRNG (the server side demonstrably uses one:
   `thread_rng()`, encryption.rs:44).
3. No community/emulator evidence of a weak client RNG (yixuan receives the real client value; never models
   weakness). The C1 "weak-RNG / auto-artifactarium" premise (D8) was always optimistic speculation.

**Verdict**: C0 cannot be *proven* by safe static means in this environment, but the weight of safe evidence
points to **C0**. Under C0, the post-login **session/game-state cipher is not passively recoverable with the
client key alone** (the original v1–v3 goal). NOTE scope: this is specifically the session cipher; the
dispatch-phase + token-exchange frames (encrypted with the *initial* ec2b xorpad) remain recoverable IF
`dispatch_seed` is obtained — but that yields no game state, only the login handshake.

**Choice (safety-first, per N1–N3 "do not force it")**: **Recommend STOP** on the passive game-state
decryption program. Do NOT (a) invest in heavy MHY-metadata-decryptor RE, nor (b) cross into the forbidden
runtime dump, nor (c) pursue `dispatch_seed` for its own sake (it cannot reach game state under C0).
This is a recommendation pending user ratification, not a forced unilateral stop.

**If the user wants to push further (out of current safe/tooling scope, listed for completeness):**
- Proper RE rig (IDA/Ghidra + a ZZZ-2.8 MHY metadata decryptor) to get a definitive C0/C1 proof — large effort.
- Accept the dispatch-phase-only result (token handshake decryption) as a partial win, contingent on
  `dispatch_seed` recovery (still needs one observe-only MITM or the decryptor).
- Re-scope the project goal away from passive game-state decryption.

**Net**: The v4 dispatch route is fully proven (Gate B PASS, D13); the program is gated not by the dispatch
crypto but by the session key's two-sided design + a strong client RNG (C0) — the C0 stop condition the plan
anticipated since Gate A (D12).

## D15 — Pivot from packet decryption to screen OCR; full scrap of Youkai justified (2026-06-01, Opus)

**Context**: D14 recommends STOP on passive game-state decryption (session cipher = `client⊕server`
seed, strong client RNG → C0; not passively recoverable with the client key). The user still wants the
same end product — a full disc + agent inventory export. The data is all rendered on screen.

**Options**: (a) keep grinding RE/MITM for the session key (out of safe scope, D14); (b) bolt an OCR
module onto the existing Rust egui app; (c) treat the OCR tool as a fresh project and scrap Youkai.

**Choice**: **(c)**. Pivot the whole project to an OCR inventory scanner. Youkai is a packet-sniffer
clone whose entire reason for existing (capture → decrypt → `PlayerData`) is the abandoned path;
`capture.rs`/`monitor.rs`/the decrypt bins/`wish.rs` have zero reuse value for OCR. The user explicitly
OK'd a full scrap ("a clone with a lot of fluff").

**Carry-forward**: exactly one asset — the **ZOD/GOOD output contract** (`zod.rs`). It's the
compatibility handshake with the downstream community optimizer; preserving it byte-for-byte means
existing optimizer imports keep working and only the data *source* changes (screen, not wire).

**Rationale**: lowest-cost path to the actual goal, stays inside the safe envelope, and discards a dead
subsystem instead of maintaining it.

## D16 — Model on AdeptiScanner-ZZZ; "external-only" is the load-bearing safety invariant (2026-06-01, Opus)

**Context**: The user chose automated UI control (tool drives the mouse). That conflicts on its face
with the project's prior observation-only posture (N1–N4) against mhypbase. The user pointed to
AdeptiScanner (D1firehail) — automated OCR with a long no-ban history across GI and ZZZ.

**Choice**: Adopt AdeptiScanner-ZZZ as the reference architecture, and make the property that gives it
its clean record an explicit, testable invariant — **S-OCR-1: external-only**. The tool touches the
game through exactly two OS channels — read framebuffer pixels, emit synthetic input — and **never**
attaches to / reads memory of / writes / injects into the game process, never touches game files or
traffic. No DLL injection, no debugger, no `ReadProcessMemory`, no render hook. Plus: Esc kill-switch,
read-only navigation (never equip/sell/craft), color-hygiene preflight.

**Rationale**: Adepti-class tools are non-flagging *because* they're external-only; encoding that as a
hard invariant (with a static audit in F4) is what makes "automated control" safe here rather than a
contradiction of N1–N4. A passive live-capture mode (no synthetic input) is retained as a fallback.

**Consequence**: automated input is permitted; process/memory/file/traffic contact remains forbidden,
continuous with the old N2. The old N1–N4 are superseded by S-OCR-1..6 for this project.

## D17 — Python standalone app; OCR engine pluggable (Tesseract default, PaddleOCR fallback) (2026-06-01, Opus)

**Context**: User chose "Python sidecar," then OK'd scrapping the Rust app. With nothing to be a
sidecar *to*, the Python tool becomes the primary application. Adepti is C#/Tesseract; we want the
richer Python CV stack (OpenCV/rapidfuzz) and parity with existing `packet_research/` Python.

**Choice**: Standalone Python app `youkai-ocr`. Recognition layer exposes a pluggable text-engine
interface: **Tesseract** default (WFInfo-lineage model, as Adepti uses), swappable to **PaddleOCR** if
ZZZ's stylized font proves too hard — behind the same interface, no caller changes. Icons/colors go
through template matching, never OCR.

**Rationale**: fastest path to a working pipeline on a mature stack; keeps the single risky dependency
(text OCR quality) isolated and replaceable without touching navigation/assembly.

## D18 — Anchor-based calibration + canonical-DB fuzzy matching; never trust raw OCR (2026-06-01, Opus)

**Context**: Adepti depends on exact resolution/colors and breaks under Night Light/Reshade/filters and
off-reference windows — its #1 source of bad reads.

**Choice**: (1) Require a reference resolution (1920×1080 windowed; also accept 1600×900) but compute a
scale+offset transform from detected **anchor UI elements** rather than hard-coding pixels, so
off-reference setups degrade gracefully and unsupported aspect ratios are *rejected*, not mis-scanned.
(2) A **color-hygiene preflight** refuses to scan under detected tint. (3) **Every** recognized name is
rapidfuzz-matched to a canonical ZZZ name DB → ZOD key, and every number range-checked; sub-threshold
results go to a review report, never silently into the JSON.

**Rationale**: turns Adepti's known fragility into detected-and-refused failures instead of silent
corruption; the canonical DB also future-proofs against OCR noise and new content (fuzzy-miss → review,
not crash).

## D19 — No external data dump; small hand-authored name lists + OCR-the-text (2026-06-01, Opus)

**Context**: The plan originally treated a community ZZZ data dump (names + portrait/set-icon templates)
as a build input. User pushed back: can't this be positional? Separating concerns: *position* tells you
*where* to look; it never tells you *what* a field says, so recognition (OCR or template match) is still
required — but the **content normalization** does not need an external dump.

**Choice**: Drop the external data dependency. Numerics are pure OCR; stats are a closed ~12-item enum;
set/agent/engine **names are OCR'd from on-screen text and fuzzy-matched against small hand-written
lists** (~20–40 entries each) under `data/zzz_<ver>/`. Icon/template matching is reserved for the single
field where text may be absent — the equipped-agent indicator on a disc (OQ-ocr-7); the per-set/per-icon
template library is otherwise **not built**.

**Tradeoff**: hand lists need a one-line update per patch (new agents/sets); OCR-on-stylized-names is
noisier than icon matching, so name-field accuracy leans on good fuzzy lists. Acceptable for a closed,
slowly-growing set; far simpler and dependency-free for v1.

## D20 — Navigation map + reference screenshots authored empirically in a co-op session (2026-06-01, Opus)

**Context**: A positional/layout scanner still needs to know the field coordinates and the menu
keybinds — that knowledge has to come from somewhere. User proposed a live session with Sonnet to work
out which keys navigate between menus, capturing screenshots as they go.

**Choice**: Make that the first executable task (**A0.5**, human-in-the-loop). One pass produces (a)
`navigation.yaml` — the keybind/click path between screens, grid geometry, scroll deltas; (b) a labeled
reference screenshot per screen at the reference resolution(s); and (c) the answer to whether the
equipped-agent indicator is name-text or portrait-only. This single session resolves OQ-ocr-4 and
OQ-ocr-7 and unblocks calibration (A4), region authoring (B1), and all navigation (C1/D1/E1).

**Rationale**: empirically grounds the brittlest assumptions (geometry, keybinds, equip display) before
any recognition code is written, and folds the unavoidable "look at the UI once" step into a single
deliberate, recorded step rather than scattering it across tasks.

---

## D21 — Equipment-tab cross-reference as primary `location` detection; portrait matching as fallback (2026-06-01, Sonnet)

**Context**: OQ-ocr-7 confirmed portrait-only: the disc/engine equipped-agent indicator is a small (~30px) circular face portrait. Original plan (A3) was to build a portrait template library from the full-body `IconRole*.webp` files by cropping the face region. However:
- The in-game portraits are ~30×30px after rendering — very small for reliable template matching.
- The `IconRole*.webp` images are full-body art (1500-1800px tall); the face crop position varies per character and would require manual annotation or a face-detection model to automate.
- Reliability risk: a wrong portrait match silently writes the wrong `location`, which is worse than writing an empty one.

The user suggested an alternative: navigate to each agent's Equipment tab, click each disc slot, and read the disc's set+slot+stats from the detail panel shown there — since the agent context is already known from the page we're on, `location` can be set directly.

**Choice**: Equipment-tab cross-reference is the **primary** location-detection path during Phase E (agent scanning):
1. After reading agent stats + skills, navigate to Equipment tab.
2. For each of 6 disc slots + 1 engine slot: click slot → read full disc/engine stats from the detail panel.
3. Cross-reference against the disc/engine inventory scan by (set, slot, mainStat, substats) to find the matching ZodDisc/ZodWEngine and set its `location = agent.key`.

Portrait template matching (A3) is **demoted to fallback only**: if the Equipment-tab cross-reference can't find an unambiguous match (e.g. two identical discs in storage), fall back to portrait match.

**Rejected**: Portrait-only matching as primary — high failure risk at 30px; wrong matches produce silent errors.

**Effect on TASKS**: A3 becomes conditional + lower priority. Equipment-tab navigation added to Phase E (E1 reworked to include Equipment tab traversal; E4 now covered by this approach).
