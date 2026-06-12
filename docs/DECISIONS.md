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

---

## D-scroll-top: scroll-to-top via scrollbar thumb, not grid hashing (2026-06-05)

**Context**: `GridNavigator._scroll_to_top()` must rewind the Drive Disc inventory to disc #1 before scanning. Ten attempts (v1–v10; see `docs/HANDOFF_scroll_to_top.md`) failed — every one either looped forever or required a fixed overshoot count that can't cover a ~2200-disc inventory.

**Root cause (the real one)**: all ten attempts detected "stopped moving" with **exact `md5`** of a grid region. md5 flips on a single changed pixel, and ZZZ continuously animates a breathing **selection-glow** (plus capture-timing jitter), so the hash *never* repeats even when the viewport is stationary. The "persistent visual change at the top" (handoff open-question #1) is that glow pulse. The attempts kept hunting for a static *region* inside the animated grid; the correct fix was to pick a signal outside the grid entirely.

**Decision**: detect scroll position from the **scrollbar thumb**. The scrollbar groove (reference x≈1360–1372) is a near-black channel containing only two static arrows and the thumb. It is untouched by selection-glow, hover, and icon animation — it changes *only* when the viewport scrolls. `_scrollbar_thumb_top()` returns the thumb's top edge in reference-Y; at the top it rests at y≈238 (threshold `SCROLLBAR_TOP_Y = 250`). `_scroll_to_top()` now wheel-ups in bursts and stops when the thumb reaches the top or stops rising.

**Why robust**: the thumb gives an *absolute* position, so wheel-up bursts (overshoot is harmless — ZZZ pins the view at the top) cannot skip the detection, only add wall-clock cost. Common case (already near top) exits in <2 s; full-bottom of a 2200-disc inventory is bounded by `SCROLL_TO_TOP_MAX_BURSTS`.

**Rejected**:
- *Tolerant (MAE) image diff over the grid* — would have worked (absorbs glow pulse) but the selection highlight is still a moving confound and the threshold needs per-rig tuning. The scrollbar is strictly cleaner: zero confounds, absolute readout.
- *Fixed wheel-event count (v6)* — can't size for an unknown, very large inventory.
- *Click-row-0 auto-scroll-up* — couples scrolling to selection changes, which is what poisoned the hash in the first place.

**Constants** (`grid.py`, reference 1920×1080): groove bbox `(1358,232,1373,872)`, bright thresh 18, top-Y 250, stall 2 px, burst 6, max bursts 80. Measured from `archive/live_20260605/preflight_discs.png` (confirmed at-top). If the thumb-at-top Y differs on another rig, only `SCROLLBAR_TOP_Y` needs adjustment; the relative "stopped rising" backstop covers minor mis-tuning.

---

## D-scan-traversal: edge-row-aware grid traversal + tolerant panel fingerprint (2026-06-05)

**Context**: `scan()` read discs diagonally — the grid scrolled mid-scan. The scanner reads the detail panel (the *selected* disc), so any unintended scroll corrupts which disc maps to which index.

**Confirmed mechanic** (user + AdeptiScanner-ZZZ source): clicking the **top** visible row scrolls up unless it is the first inventory row; clicking the **bottom** visible row scrolls down unless it is the last; middle rows never scroll.

**Decision**: traverse with that mechanic. Start at the top (scrollbar rewind guarantees it → row 0 safe), read rows 0..rows_visible-2 in place, use the bottom row purely as a scroll trigger, and re-read the second-to-last row after each scroll until its discs stop changing. Detect scroll completion / end-of-inventory by a **tolerant** detail-panel fingerprint (downscaled grayscale, mean-MAE), never exact hashing.

**Why tolerant fingerprint**: every prior exact-hash scheme (grid region or panel) was defeated by the breathing selection-glow and capture jitter — a single changed pixel flips an md5. A downscaled-MAE comparison absorbs that noise while still separating distinct discs. The panel region is also clear of the grid's selection glow.

**Rejected**:
- *Transplant AdeptiScanner's C# wholesale* — keep our better infrastructure (natural Bezier clicks, scrollbar rewind); port only the row-management insight.
- *Exact panel hash* — brittle (see above); a false "changed" at the bottom would loop forever emitting duplicates.
- *AdeptiScanner's click-probe top-confirmation* — unnecessary; our scrollbar thumb is a cleaner "are we at the top?" signal.

**Known limits**: assumes scroll-to-top reaches the absolute top; two pixel-identical discs straddling a trim boundary could be over-trimmed (same edge AdeptiScanner has). See `docs/LOG_ocr.md`.

---

## D-scan-count: deterministic grid traversal from the disc count (2026-06-05)

**Supersedes the content-detection part of D-scan-traversal.** Using detail-panel fingerprints to decide "did we scroll" / "is this row empty" failed: measured on real panels, the **minimum** MAE between *different* discs is 0.57 (median ≈ 6). ZZZ has many near-identical/duplicate discs, so no content threshold can separate "same disc" from "different disc" reliably → infinite re-capture loop.

**Decision**: read the current disc count from the "Drive Disc Storage [ N / M ]" header (OCR, regex) and traverse a deterministic `ceil(N/9)` rows, truncating the last row to its real width. No content comparison in the control flow → no possible loop, exact end, correct partial last row. The scrollbar thumb only *confirms* each down-scroll landed (alignment), never decides termination.

**Kept**: edge-row-aware traversal (top/middle safe at the top, bottom row = scroll trigger), natural Bezier clicks, scrollbar rewind. **Removed**: panel fingerprint + tolerant row matching.

**Fallback**: if the count can't be read, scroll until the thumb pins at the bottom (`_scan_by_thumb`) — imprecise last-row width but loop-safe.

**Risk**: depends on the header count OCR (clean large text; verified =2200). If miscounted, the row math is off — sanity-check the count against discs yielded.

---

## D-ocr-pipeline: desynced capture + OCR worker pool, OCR-paced clicking (2026-06-05)

**Context**: navigation + reads confirmed correct (verified from saved frames). Bottleneck is OCR: 7 serial tesseract calls/disc ≈ 2.7 s/disc ≈ 1.5 h for 2200 discs. The old flow OCR'd on the navigation thread, stalling per row.

**Decision**: producer/consumer pipeline. Navigation (main thread) captures frames and feeds a **bounded** job queue; a pool of OCR worker threads drains it in parallel (pytesseract shells out per call → threads parallelise; recognizer is stateless/shared). The bound gives backpressure so **navigation never clicks faster than OCR drains** — bounding memory and keeping clicks human-paced. `_read_row` became a per-cell generator so backpressure pauses *between discs*. A `CAPTURE_MIN_INTERVAL_S` floor keeps cadence human even when OCR is fast (anti-ban). Results keyed by cell_idx, reassembled in order.

**Why (anti-ban tension)**: making OCR fast would otherwise uncap the click rate into bot-like territory. Capping capture to OCR throughput + a cadence floor keeps input human while still ~Nx faster. Natural Bezier clicks unchanged.

**Rejected**: capture-everything-then-OCR (3 GB of frames); in-process tesseract / fewer-calls-per-disc (good complementary speedups, deferred — lower ceiling than parallelism, can add later); caching identical panels (unsafe given near-identical discs).

---

## D-render-gate: verify the detail panel rendered before accepting a capture (2026-06-05)

**Problem**: the live full scan dropped ~1038/2200 discs. Root cause (LOG 2026-06-05 triage):
ZZZ fades the detail panel in on every selection change; the D-ocr-pipeline cadence
(`CLICK_DELAY_S=0.09`, ~0.4 s/disc) captures **before render completes** → blank/dim panels
(`disc_2100` blank, `disc_1200` mid-fade) → `set_conf<30` critical-fail. Speeding up clicking
outran the render.

**Decision**: stop trusting a single fixed-delay capture. After click + base settle, capture and
**gate on render**: measure mean luma of the panel/title region; if below a floor (blank/mid-fade),
sleep a short step and re-capture, up to a timeout, then proceed with the best frame. Also raise the
base `CLICK_DELAY_S`. This is adaptive (pays render time only when needed) and preserves the
anti-ban human cadence floor.

**Rejected**: (a) blind large fixed delay everywhere — wastes time on fast-rendering panels and is
still not guaranteed; (b) re-OCR the archived blank panels — the disc was never on screen, so the
pixels don't exist; retry must be live; (c) content-hash "did it change" gating — already rejected
(D-scan-count) because near-identical discs defeat it.

**Risk**: a luma floor must distinguish "blank panel" from "legitimately dark disc art" — gate on the
**title/text** sub-region (always bright text when rendered), not the art.

---

## D-count-everywhere: W-Engine scanner adopts the count-driven traversal (2026-06-05)

**Problem**: `wengine_scanner` called `navigator.scan()` with no count → `_scan_by_thumb` fallback;
the live run read 225 cells for 222 engines (3 phantom empties, no exact last-row width).

**Decision**: read `W-Engine Storage [ N / M ]` (mirror `disc_scanner.read_disc_count`, same header
style, confirmed present in `preflight_engines.png`) and pass `total` to `navigator.scan(total)`.
Reserve `_scan_by_thumb` strictly for the count-unreadable fallback, as on discs.

---

## D-agent-geom: agent navigation coordinates require live re-measurement (2026-06-05)

**Problem**: agent portrait detection scanned `(0,32,1920,75)` @ Y=53 — a full-width band *below*
the real portrait strip (top-right, ~x810–1300, y≈2–28). It locked onto character splash-art and the
stats panel, clicked off-target, and eventually hit **City**, exiting the menu. The agent geometry
was never validated against a live frame (first run to reach Phase E).

**Decision**: treat all Phase-E coordinates (portrait strip bbox + click-Y, tab centers, equipment
slot centers, base/skills field bboxes) as **unvalidated** until measured from real archived agent
frames (`preflight_agents.png`, `agent_000/*`). Constrain the portrait x-range so splash-art can't be
detected; re-derive the strip Y from the actual thumbnails. Gate the next live agent run on this.

---

## D-slot-panel-fallback: recover the slot from the un-clipped panel, two-pass, when title parse fails (2026-06-06, Opus)

**Context**: After G1 (render-gate) + the tolerant slot regex, 12 structural disc `no_slot`
fails persist (8 Fanged Metal, 4 Dawn's Bloom) — root-caused offline (LOG 2026-06-06). The
slot is *visible and correct* on every one; only the title-text OCR fails to yield it, for two
distinct layout reasons: long names clip the title `[N]` past `_TITLE_BBOX` x=1660 (Fanged
Metal), or wrap `"Name [N]"` to two lines where psm-6 + watermark noise drops the `[` (Dawn's
Bloom).

**Options weighed**:
- *Detail-panel slot badge* (hexagon `③`): rejected — its Y shifts with title line-count and the
  metallic ring OCRs as a spurious `1`; fixed-bbox single-char reads 2/12.
- *Widen `_TITLE_BBOX`*: rejected — the disc icon art starts ~x1651, inside the slot x-range, so
  widening injects icon noise.
- *Grid-cell thumbnail slot digit* (fixed offset from the known cell center, set/layout-independent):
  the most robust source in principle, but **cannot be validated offline** (no archived full frames
  for the failing discs; `live_20260606` captured the wrong window). Recorded as the future-proofing
  path, not adopted now.
- **Two-pass panel slot OCR** (chosen): run a digit+bracket-whitelisted pass (psm 11) over the
  *un-clipped* panel — Pass A (x[0:300] y[158:210]) catches 1-line names whose slot is pushed right;
  Pass B (x[0:180] y[200:290], excluding the bright icon) catches 2-line names whose slot wraps
  left-low. First `[1-6]` wins, bracketed preferred. **Offline-validated 12/12** against the archived
  panels; a single unified crop only reaches 7/12.

**Choice**: add this as a tier-3 fallback inside `parse_slot`/`_extract_disc` (tier-1 title text
unchanged; runs only on the ~0.5% that fail it, so no cadence cost). Implement as **G5** with the 12
archived panels committed as test fixtures.

**Risk / known limit**: the two crop windows are tuned to current ZZZ panel geometry (1-line vs
2-line title). A future set with an even longer name (3-line title?) or a re-laid panel would need
re-tuning — at which point migrate to the thumbnail-digit source (validate live then). The fallback
is gated to `no_slot` cases only, so it can never *worsen* a currently-passing disc.

## D22 — Roster traversal = detect-page + scroll-until-stable + pHash dedupe (no count header) (2026-06-06, Opus)

**Context.** Discs/engines have a `[N/M]` header driving count-based traversal; the agent screen
has none, and the top portrait strip is a horizontal scrolling list. The old scanner detected
portraits from frame 1 only and never scrolled (RC-2).

**Decision.** Traverse by: detect all portraits on the current strip frame → visit each un-seen one
→ scroll horizontally (mechanism settled by live probe H0) → repeat. Dedupe by perceptual hash of
the portrait thumbnail (primary); repeated agent-key is a secondary end signal. Terminate on strip
frame-hash stability (adapt the `grid.py` scroll-stability pattern), or no new portraits, or key
repeat; hard cap `AGENT_MAX=60`.

**Rejected.** (a) Count-based traversal — no header exists. (b) Detect-once — the documented bug.
(c) OCR a roster-size from a menu — not reliably shown on this screen.

**Consequence.** New `seen`-set + scroll loop in `AgentNavigator`. The scroll mechanism is the one
unknown; resolved by probe **before** building the loop (see D23 lesson). Tasks H0–H2.

## D23 — Every in-screen navigation step gets a render-gate; geometry is measured from reference frames, never assumed (2026-06-06, Opus)

**Context.** This session proved the live "Equipment" frames were actually **Skills-tab** captures
(RC-3): the `_TAB_EQUIPMENT` click never activated Equipment, and slot clicks hit the Skills-tab
core nodes. Independently, the disc/engine slot centers were ~350px too far left vs
`reference_7` (engine center ≈ (1418,590) vs coded (1038,515)) — `navigation.yaml` still carried an
un-actioned `TODO: refine slot centers from ref_7`. Both defects came from authoring geometry by
assumption and from no step verifying it landed.

**Decision.** (1) Mirror G1's render-gate at **every** agent nav step (tab activation, slot panel
open): assert the expected screen rendered (luma/template predicate) and re-capture-then-log on
failure — turn silent wrong-screen captures into loud, recoverable issues. (2) All agent geometry
(roster strip, tab centers, slot centers, equip title) is re-measured from `reference_{3,4,7,8,9,10}`
and verified by an offline assertion before any live run.

**Consequence.** Tasks H1, H3. The gate predicate is itself unit-tested (True on ref_7, False on a
skills frame). This is the durable fix for the class of bug that produced 3 dirs of useless frames.

## D24 — Validate agent extraction offline against reference fixtures before any live run (2026-06-06, Opus)

**Context.** Name/level/ascension/mindscape/skills/core/equip extraction was implemented but the
3 captured agents' values were never checked (no stdout saved; only frames archived). Ascension and
core-rank are admitted heuristics.

**Decision.** Build offline fixtures from `reference_{3,4,9,10}` (mirror the G5 disc-slot fixture
pattern) and assert known values (Zhao / Lv.60 / skills 12,10,11,12,11 / equip set+slot) via the
existing `scan_single_frame_agent`. Fix bboxes; route still-uncertain heuristics to low-confidence
→ F3 review report rather than trusting them. **No live agent run until these pass.**

**Consequence.** Task H4. Removes the "captured but never validated" failure mode for good.

## D25 — Tandem `scan-all`: keep manual menu gates, but make runs self-documenting + resumable (2026-06-06, Opus)

**Context.** `scan-all` already chains discs→engines→agents→`resolve_locations`→merged export with
`input()` gates between the three top-level menus. The last run lost all stdout (counts/assembly
results unrecoverable from disk) and captured the wrong window.

**Decision.** Keep the manual `input()` gates between the three *menus* (AdeptiScanner parity per
D20/D-nav; auto-opening different top-level menus is out of scope). Add: (1) `archive/<run>/scan.log`
tee + `results.json` (per-phase counts/issues/export) so runs are auditable from disk; (2) a
per-phase preflight screen-assertion that aborts loudly on the wrong screen (would have caught the
Game Pass-launcher capture); (3) per-phase output files enabling agent-phase resume without
rescanning 2210 discs.

**Rejected.** Full auto-navigation between menus — fragile, marginal benefit, against the established
manual-menu convention. Logs-only without results.json — still not machine-auditable.

**Consequence.** Task H5. Supersedes nothing in D21 (Equipment cross-ref remains the primary
`location` path); makes that path finally exercisable end-to-end.

## D26 — Full menu auto-navigation via the main-menu hub (supersedes D25's manual-gate stance) (2026-06-06, Opus)

**Context.** D25 kept manual `input()` gates between the three top-level menus because no map of the
hub existed. The user supplied it: `reference_11` (main menu) has `Storage` and `Agents` buttons; a
universal red back-arrow (top-left, on every screen) returns to the hub. `reference_12` (agent menu)
→ `Base` opens the agent stat page. Storage is a **single** screen — `reference_1`/`reference_2` show
the same 4 top-right category tabs with the active one glowing (W-Engine yellow → Disc green), so
engine↔disc is one tab click, not a menu round-trip. The active-tab glow pulses but always brightens.

**Decision.** Build a single auto-navigating `scan-all` (task H7): main-menu → Storage → (engine tab,
scan) → (disc tab, scan) → back → Agents → Base → agent page → (Phase H roster scan) →
`resolve_locations` → merged export. Every transition is wrapped in a render-gate (D23); the
category-tab glow IS the storage-screen gate (threshold the 4 tab bboxes, pick the brightest =
active sub-tab). Keep manual `input()` gates only as a `--manual-nav` fallback.

**Rejected.** Keeping manual gates (D25) — the hub map removes the fragility that justified them.
Treating Storage as two separate menus — it's one screen with category tabs.

**Consequence.** Task H7. Needs button coords from ref_11/ref_12 (Storage/Agents/Base), a
`return_to_main()` primitive (back-arrow), and per-screen signatures. Anti-ban profile unchanged
(synthetic UI clicks, external-only). Supersedes D25 on the gate question; D25's persistence +
resume + preflight-assert points still stand and reinforce H7.

## D27 — Agent roster traversal via the agent-menu GRID (reuse grid.py), not the detail-page top strip (2026-06-06, Opus)

**Context.** The handoff + early plan (RC-1/RC-2, H1/H2) assumed the roster is the cramped horizontal
portrait strip atop the agent *detail* page (ref_3), requiring bespoke strip detection + horizontal
scroll. `reference_12_agent_menu.png` shows the agent *menu* roster is a **2D grid** of portraits on
the right (Lv + promotion stars per cell) with `Base`/`Skills`/`Equipment` buttons — the same kind of
surface as the disc/engine inventories. Reached from the bottom-bar `Agents` button (ref_11).

**Decision.** Enumerate the roster by traversing the agent-menu grid with the proven `grid.py`
machinery (detect cells → click → scroll-down → dedupe → stability end-detection), count-free
(`AGENT_MAX=60`). Per selected agent, enter Base/Skills/Equipment from the detail page and capture as
in H3. The detail-page top strip is ignored for enumeration. This dissolves RC-1 (strip band) and
RC-2 (no scroll); only RC-3 (Equipment tab reach + slot geometry + render-gate) remains.

**Also recorded (user decision, 2026-06-06):** keep **full automation including the Equipment tab**
and derive disc/engine `location` from the **Equipment-tab cross-reference** (D21 stands) — not a
screenshot-only agent pass and not inventory-thumbnail portrait matching. So Phase H keeps H3/H4 in
full; do not re-open "simplify agents."

**Consequence.** H0/H1/H2 reframed to grid traversal; H7a unblocked (ref_11/ref_12 readable in
`screenshots/`). New `navigation.yaml:agent_menu` section. Grid cells are large/well-separated, so
enumeration rides on already-working code — the main remaining risk is RC-3 and the agent-grid scroll
stride (H0 tuning).

## D28 — Agent-grid: blob-detect owned cells (skip locked/unowned), traverse with loop-around dedupe end (2026-06-06, Opus)

**Context.** `reference_13/14` (agent menu scrolled) show: (1) the roster grid is **sheared**
(diagonal layout, not rectilinear) and scrolls vertically over multiple pages; (2) the grid contains
**unowned** agents — grayscale portraits with a **padlock on the rarity star**, "Lv. 1", plus an
"EMPTY CHARACTER" placeholder — which must be ignored (user: "locked = not owned"); (3) there is no
reliable scroll-to-top, but the list can be traversed in one direction and "looped around".

**Decision.** (a) Detect grid cells by **saturation-thresholded blob detection** over the grid region
rather than fixed col/row pitch — this absorbs the shear and yields click-centers directly. (b)
**Ownership filter:** keep only colored/high-saturation portraits with a gold star; drop padlocked
(desaturated) cells and "EMPTY CHARACTER". (c) **Traversal:** reuse only `grid.py`'s
scroll/stability/dedupe loop; scroll one direction, dedupe owned cells by perceptual hash, and end
when a page produces no new owned agent (locked tail reached or wrap/loop back to a seen agent). No
scroll-to-top needed. Cap `AGENT_MAX=60`.

**Rejected.** Rectilinear fixed-pitch cell model (grid.py default) — breaks on the shear.
Scroll-to-top anchoring (as discs do via the scrollbar thumb) — user says there's no reliable first
position; loop-around + dedupe makes it unnecessary.

**Consequence.** H1 = blob detector + ownership classifier; H2 = scroll/dedupe/loop-around end.
Refines D27. Fixtures: ref_12 (owned page), ref_13 (mid), ref_14 (locked tail).

## D29 — Enumerate agents via the detail-page top strip, not the sheared menu grid (supersedes D27/D28 for traversal) (2026-06-07, Opus)

**Context.** D28's saturation-blob grid detector was specified but **never implemented** — H1 shipped a
fixed **2-column** model (centers 1407/1667) that "passed" only by validating against itself (LOG
2026-06-07, RC-1). The live roster is **3 sheared columns** (≈1180/1460/1740); 1407/1667 fall in the
**gutters** → `agent_nav_fail cx=1407 cy=144` → 0 agents. Attempting D28 properly, **three** offline
detectors (luma columns, gold-star blobs, saturation blobs) all failed to segment the grid: portraits
are packed edge-to-edge, all saturated, cells are parallelograms, and badges/coins add noise. The
sheared, packed, scrolling grid is the wrong substrate for reliable fixed-input clicking.

**Decision (user-approved 2026-06-07).** Enumerate agents through the **agent detail page's top agent
strip** (ref_3): a clean, regular **horizontal** row of thumbnails (measured pitch ≈ 60px, y≈43,
x≈1180–1850, `<`/`>` scroll arrows at the ends) on a dark background — trivially segmentable vs the
grid. Flow: from the agent menu, click any one owned agent **once** to enter the detail page (this is
the only click that triggers the "AGENT SELECT" wipe), then iterate by clicking each strip thumbnail
(switching agents *within* the detail page — expected to skip the wipe), reading Base/Skills/Equipment
via the bottom tabs (H3 geometry unchanged), pHash-dedupe, scroll the strip via `>`, end when a scroll
yields no new thumbnail. The sheared menu grid is used only for the single entry click.

**Rejected.** Fixed 2-column grid (RC-1, the bug). Live-tuned blob grid detector (D28) — the offline
evidence says it stays fragile; the strip is strictly easier and likely also dodges the wipe.

**Open (needs the H10 live probe — cannot be settled from static frames):** (1) does clicking a strip
thumbnail switch agents **without** the full-screen wipe? (2) does the strip contain **all** owned
agents (vs only team/recent)? (3) `>`-scroll stride + does it loop? Build the H8 loop against the probe
answers; do not build blind.

**Consequence.** D27/D28 superseded **for enumeration** (their RC-3/H3 equipment work + D21 location
cross-reference stand). H1's grid detector retired. New tasks: H8 = strip-traversal; H10 = live probe.
RC-2 (yellow active-tab predicate + Base/Skills render-gates) implemented this session, needed in any
path. Implements the still-open half of D23 ("render-gate every nav step").

---

## D30 — Equipment-hexagon disc coords: the old "wide" coords were wrong; validate by ring geometry, not center saturation (H11→H12, 2026-06-07)

**Context.** The H3 equipment-slot geometry ("wide" coords, x-span 1088–1785) was taken from
`reference_7` using a center-**saturation** test, and the first live run missed every disc click.

**Investigation.** H11 re-measured from the live archive (compact, x-span 1137–1662) and I *initially*
mis-theorised that ref_7 was a "zoomed-up" layout. **H12 disproved that:** HoughCircles ring geometry on
reference_7, reference_15, reference_16 AND the live archive all return the SAME compact disc centers
(±2px). The user confirmed ref_16 (equipment tab) and ref_15 (disc-select) are accurate to the live
client and that the hexagon does not move between them. The "wide" coords never pointed at discs at all
— they passed the old saturation test only because they happened to land on the colorful background
**filmstrip art** behind the hexagon in ref_7 (a false positive).

**Decision.** Use the compact coords (correct for all sources). **Validate disc geometry by the rarity
RING annulus (set-independent: ≥55 on a slot vs ≈20 off-disc), not center saturation** — a disc's
central icon can be dark/muted (ref_16's blue discs read ~24 at center but ~97 on the ring), which is
exactly the trap the original test fell into. The H3 disc test now runs against `reference_16` (committed
to `reference/`). ref_7 is kept only for the engine-bright + panel-dark gates. The hexagon is identical
on the equipment tab and the disc-select view, so one coordinate set covers all 7 slot clicks per agent.

**Deferred.** Runtime hexagon detection (HoughCircles per session) remains the robust long-term guard
against future layout/zoom drift, but is unnecessary now that four independent sources agree. Defer.

---

## D31 — Tab capture gates on CONTENT rendered + re-clicks dropped clicks; equipment stays content-ungated (H17, 2026-06-07, Opus 4.8)

**Context.** Live run after H16: the Equipment tab "moused over but never clicked." Archive proof —
`agent_000/equip_slot_*.png` were all the still-open **Skills** page, and `agent_000/skills.png` itself
was banked **mid-animation** (Skills pill yellow, no nodes painted). The Equipment click fired *during*
the Skills entrance animation and the game silently dropped it.

**Two root causes in `_capture_tab`.** (1) The render gate only **re-CAPTURED** on a miss, never
**re-CLICKED** — so a dropped click is unrecoverable (the pill never changes), unlike `_enter_detail_page`
and `_advance` which already re-click. (2) The gate keyed only on the **yellow pill**, which lights when a
tab is *selected*, **before** its page content animates in — so even a "passing" capture can be
half-painted.

**Decision.**
1. **Re-click on dropped clicks.** `_capture_tab` polls (`_TAB_GATE_POLLS=8` × `_TAB_GATE_POLL_S=0.35`)
   and re-clicks the tab every `_TAB_RECLICK_EVERY=3` polls while the pill is not yellow.
2. **Gate on content, not just selection.** Require pill-yellow AND `_tab_content_rendered(frame, tab)`,
   an agent-INDEPENDENT signal: base = agent-name luma `>30`; skills = mean skill-level luma `>40`
   (measured from the live mid-anim frame vs the same page rendered, cross-checked vs reference_3/4).
3. **Do NOT content-gate Equipment.** Its only agent-universal element (the engine hexagon) reads dark on
   an **unequipped** W-Engine → a content gate would false-fail; and the equipment-tab frame feeds no OCR
   (the per-slot frames do, each already gated by `_slot_panel_rendered`). Equipment keeps pill + re-click
   only. This is why the H3 `_equip_tab_rendered` hexagon check stays a **warning**, not a gate.

**Rejected.** Core-node teal as the skills signal — it is **mindscape-dependent** (a low-investment agent
lights few nodes → low teal even when fully rendered) and would false-fail. Skill-level boxes are always
present regardless of investment. Also rejected: a fixed post-pill sleep — animation duration varies; a
measured content predicate is robust where a magic delay is not.

---

## D32 — Confirm agent moves on the character render, not the strip band; gate every equipment slot; reactive (not blind) trial-skip (2026-06-07, Opus 4.8)

**Context.** Live feedback after H17 (LOG H18): the 2nd equipment slot frequently never got clicked;
`>` navigation occasionally skipped 1–2 agents; empty slots (Koleda) were mis-recorded; trial agents
(Nangong Yu) hung the pass on a "not available in preview mode" modal.

**Decision 1 — advance/ring-closure key on `_CHARACTER_RENDER_BBOX`, not `_STRIP_PHASH_BBOX`.**
A single `>`/`<` moves only the one-thumbnail selection highlight (the filmstrip does not scroll
except at an edge — H10-Q3), so the strip band changes too little to detect a real move. `_advance`
then re-clicked and double-advanced → skipped agents. The big full-body render changes completely on a
move and is present on every detail tab (ref_7/16). New `_agent_id()` + `_AGENT_CHANGE_MIN_BITS` /
`_AGENT_RING_CLOSE_MAX = 15`. *Rejected:* tightening the strip bbox to the selected thumbnail — its
exact pixel position is unknown without a live measure, and the render is unambiguous regardless.

**Decision 2 — render-gate every equipment slot with re-click (`_open_slot`).** The first slot opens
the disc-select view with a slow layout wipe; a 2nd click during it is dropped (H17 class). Slot 0
gates on the panel appearing; slots 1+ gate on the panel-title pHash switching from the prior slot,
re-clicking on a miss. *Rejected:* an inter-slot Escape to re-enter from a clean hexagon each time —
slower and contradicts the H10-Q4 confirmation that slots stay clickable; the drop is purely a
first-open timing issue the gate handles. Also raised `_SLOT_CLICK_DELAY_S` 0.20→0.45 (the downstream
per-agent OCR pause means there is no throughput cost to waiting).

**Decision 3 — trial agents handled by a BOUNDED REACTIVE net, not a blind proactive detector.**
When the Equipment hexagon never renders, Escape (dismiss the modal) and return `_EQUIP_UNAVAILABLE`
→ `scan()` skips the agent (no export, no false location). *Rejected for now:* a proactive "skip
before scanning" using the dark engine hexagon — an OWNED agent with an empty W-Engine (Koleda) reads
the hexagon dark too, so that signal would mis-skip real agents. Proactive trial-skip is deferred
until a Nangong Yu reference exists (do not calibrate blind — the RC-3 lesson). The bounded slot loop
plus this net already remove the live HANG.

**Deferred (needs live reference frames).** Empty-slot tracking (issue #3 — Koleda frame) and
proactive trial detection (issue #4 — Nangong frame). Designed in DESIGN_agents.md H18; not
implemented to avoid blind thresholds.

---

## D33 — Empty-slot detection keys on the EMPTY signature; fix reversed disc-slot numbering (2026-06-07, Opus 4.8)

**Context.** Koleda reference (`reference_17`, fully unequipped) received. User: equipped sets have many
colour schemes but the unequipped state is distinctive.

**Decision 1 — detect the EMPTY signature, not the (varied) equipped ones.** Disc empty = dark center
(luma <80; equipped ≥120 across all schemes). Engine empty = the "core available" glow = high
colored-frac AND moderate luma (`>0.15 AND <150`); the luma guard rejects a hypothetical bright
colourful engine (only one equipped-engine sample exists → OQ-H18c live confirm). `_read_equipment`
skips empty slots (no click → no false inventory-disc location) and Escapes only if a panel opened.
*Rejected:* clicking every slot and filtering by panel OCR — that is exactly the corruption path (an
empty slot's panel shows the first inventory disc with high confidence).

**Decision 2 — fix the reversed disc-slot numbering (`slot# = 6 - idx`).** Koleda's empty slots show
their in-game numbers: the hexagon is 1,2,3 (left, top→down) then 4,5,6 (right, bottom→up), so
`_DISC_SLOT_CENTERS[0]` (upper-right) is slot 6. The prior `slot_idx + 1` was reversed and would have
made every `resolve_locations` disc match miss. New `_slot_number()`; ground-truthed by
`test_slot_number_mapping_matches_koleda_layout`.

**Decision 3 — keep the issue-4 reactive net as-is.** Verified Koleda's empty engine still passes
`_equip_tab_rendered` (gate-window luma ≈110 > 80), so the net does not mis-skip a real owned agent
with no engine. Proactive trial-skip still deferred to a Nangong frame (D32 stands).

## D34 — Slot switch-detection gates on the panel BODY + a stability check, not the title alone (H19, 2026-06-08, Opus 4.8)

**Context.** Live feedback round 3, after H18 shipped: "disc 2 still skipped sometimes," "errors from
having to click repeatedly," and a new "hangs oddly on disc 4." All three trace to the H18 slot-open
gate, which keyed on the disc TITLE region (`_EQUIP_TITLE_BBOX`).

**Decision 1 — gate the slot switch on the detail BODY (`_SLOT_DETAIL_BBOX = (610,120,965,600)`), not
the title.** Two adjacent slots holding the SAME disc set (4-piece sets are the norm) have
near-identical titles, so the title-pHash Hamming stayed ≤ `_SLOT_CHANGE_MIN_BITS` even on a real
switch → the gate never fired → 8 polls of futile re-clicking (`slot_gate_fail`) = the "clicking
repeatedly" noise and the ~2.8s disc-4 "hang." The center panel's main-stat + substats DIFFER between
two discs of one set (confirmed on `reference_8`), so the body is a reliable switch signal where the
title is not. *Rejected:* detecting which hexagon carries the yellow-green selection ring — more robust
in principle but needs a measured highlight signature we don't have; the body pHash is sufficient.

**Decision 2 — require the panel to be STABLE across two captures before banking
(`_SLOT_STABLE_MAX_BITS = 6`).** The title gate also false-POSITIVED on a half-faded panel: a mid-fade
frame differed enough from the previous slot to look "switched," so a duplicate of the previous slot
was banked → the missing disc read as "skipped." Requiring two consecutive matching body captures means
a mid-animation frame is never accepted. A panel that settles UNCHANGED from the previous slot is a
genuinely dropped click → re-click (the H18 recovery, preserved).

**Decision 3 — settle the Equipment-tab frame before empty-detection (`_wait_region_stable` on
`_EQUIP_RING_BBOX`).** `_capture_tab` returns the instant the yellow pill lights, BEFORE the hexagon
disc icons fade in. `_disc_slot_equipped` then sampled a half-faded icon (luma < 80) and mis-flagged an
EQUIPPED slot as EMPTY → skipped (the other half of "disc 2 skipped sometimes"). We now wait for the
ring region to stabilize first. Tolerant 12-bit budget: the fade-in changes the whole ring (huge ΔpHash)
while the one-slot selection-glow pulse is small. `_open_slot` returns `(frame, body_pHash)` so the next
slot compares like-for-like instead of the caller recomputing a title hash.

## D35 — Equipment render-gate must key on the disc ring, not the engine center (H20, 2026-06-08, Opus 4.8)

**Context.** Live feedback: `equip_unavailable — hexagon not rendered after tab switch` fired on a real,
fully-geared owned agent. The captured frame (`archive/live_20260605/nav_equip_unavailable.png`) shows a
FULLY rendered Equipment tab: all 6 disc hexagons equipped (Lv. 15/15) and an equipped Lv. 60/60
W-Engine. The agent was silently dropped from export (`agent_skip_trial`).

**Root cause.** `_equip_tab_rendered` keys the render-gate on engine-center luma > 80
(`_EQUIP_GATE_CENTER=(1398,515)`, r=20). The engine slot is the single most agent-variable region on the
tab. Measured on the failing frame: engine-center luma = **78.3** (fails >80 by 1.7) because this
W-Engine's render is dark "rocky" art. Meanwhile the 6 disc slots read 114–160 (all clearly equipped)
and the ring bbox `(1100,280,1720,800)` has std 63 / gradient-edge-frac 0.142 — unmistakably rendered.

This **falsifies D33-Decision-3**, which claimed the reactive net is safe because "Koleda's empty engine
passes the gate at luma ≈110." That only checked an *empty* engine's glow; it never checked an *equipped*
engine with dark art, which sits right at the threshold. The gate is brittle on a ~2-luma margin keyed to
the one region that varies most by agent/engine — so it false-skips real agents two ways: (a) empty
W-Engines whose glow dips under 80, and (b) equipped W-Engines with dark art (this case).

**Decision.** Re-key the render-gate to the disc ring, which is agent- and engine-independent. Treat the
Equipment tab as rendered if **any disc slot reads equipped** (`_disc_slot_equipped`) OR the engine reads
bright (the existing `_EQUIP_GATE_LUMA_MIN` luma check). This is exactly the **union** of the old gate and
the new disc path, so it strictly *widens* "rendered" → it can only remove false skips, never add them.
The disc path rescues every agent wearing ≥1 disc (the live frame: 6 discs + dark engine); the engine-luma
path uniquely still catches a fully-naked owned agent, because an EMPTY W-Engine shows the bright "core
available" glow (Koleda: luma≈110), well clear of a skills/base page (luma≈39).

**Rejected — a ring-bbox structural floor (gradient-edge-frac).** Initially added as a third "rendered"
signal for the naked-agent case, then *empirically refuted by measurement*: edge-frac does NOT separate a
genuinely-rendered empty hexagon (Koleda **0.034**) from a non-equipment skills page (**0.053**) — an empty
ring is *less* busy than a content-filled page, so the empty hexagon scores lower than the very frame the
gate must reject. Edge density in that bbox tracks page content, not hexagon presence. Removed.

**Rejected:** raising the `_EQUIP_GATE_LUMA_MIN` margin or moving the engine window — still keys on the
most-variable region; any threshold is fragile against dark engine art. **Rejected:** dropping the gate
entirely — the H18 anti-hang purpose stands; trial/preview agents must still be escaped.

**Residual gap (carries OQ-H18b).** One case neither signal covers: an agent with **zero discs AND a dark
equipped-engine render** (luma < 80). It is vanishingly rare (who runs an engine but no discs?) and, more to
the point, *indistinguishable* from a trial/preview frame without the deferred trial reference (H18.4b /
Nangong) — so it is intentionally out of scope. The old engine-only gate also failed this case, so there is
no regression. `_is_owned_agent` already backstops trial filtering upstream; proactive trial-skip remains
the deferred H18.4b path. The data-loss bug (dropping real geared agents) was the higher cost; the union
gate fixes it without new calibration risk.

---

## D36 — Per-slot empty-detection must be POST-CLICK content validation, not a pre-click pixel guess (H21)

**Context.** Live (2026-06-08, `--agents-only --debug-overlays`, 5 agents): all 5 got 6/6 disc slots, but the
**engine was captured on only 1 of 5**, and `equip_slot_6.png` was stale (prior run) for the rest. The engine
is being *skipped*, not mis-clicked — a skip writes `frames.append(None)`: never clicked, never captured.

**Root cause (measured, not assumed).** `_engine_slot_equipped` decides empty BEFORE clicking, from
saturation+luma on the hexagon overview. The classes do not separate on those axes:

| frame | state | colored | luma | `equipped()` |
|---|---|---|---|---|
| ref_7 | equipped (bright) | 0.022 | 210.5 | True ✓ |
| ref_16 | **equipped** | 0.287 | 134.0 | **False ✗ (false-empty)** |
| `nav_equip_unavailable` | **equipped** (dark) | 0.834 | 78.7 | **False ✗ (false-empty)** |
| ref_17 Koleda | empty | 0.526 | 89.3 | False ✓ |

The genuinely-empty engine (0.526 / 89) sits *between* the two equipped engines (0.287/134 and 0.834/79).
No luma or colored-frac threshold separates them; hue-std doesn't either (empty 32.8 ∈ equipped 2.8–62.0).
Only a bright low-saturation engine (ref_7) survives → engine captured ~1/5. This is the **same lesson as
D35's rejected edge-frac fallback**: a per-slot pixel heuristic on the most agent-variable region cannot be
calibrated to separate equipped from empty.

**Decision.** Stop pre-classifying empty from overview pixels. Move to a **closed-loop per-slot contract**:
click → confirm the selection panel opened (`_slot_panel_rendered`, already exists) → validate the **center
detail pane by CONTENT** — an equipped slot renders title + `Lv. N/N` + substats (ref_8/9/10); record the
slot iff that content parses ≥ `_EQUIP_CONF_MIN`, else treat as empty (no record, `location=""`). Content is
an OCR-confirmable signal; overview pixels are not. This also gives the per-item completion gate the design
has been missing: a slot is "done" only when its panel is confirmed parsed-or-empty.

**Blocker / required input (the RC-3 discipline — do NOT guess).** We have references for the *equipped*
selection screen (ref_8/9/10) but **none for "clicked a genuinely empty slot."** ref_6 is the W-Engine
*Storage* inventory, not an agent's empty-engine click. The open risk (H18's stated corruption bug): clicking
an empty slot may auto-select the first *inventory* item and render ITS title center → a false location. We
cannot tell whether the empty-slot center pane is blank or auto-populated without the frame. **Action:** with
Koleda (fully unequipped, ref_17) capture two frames — click an empty *disc* slot, and click the empty
*engine* — to calibrate the post-click empty signal. Until then any post-click parse is unsafe for truly-empty
slots.

**Interim (engine-only, optional).** If the engine must be recovered before the refactor: the dominant cost is
false-empty (proven 4/5), and `_is_owned_agent` already filters trial agents upstream, so bias the engine to
"click + parse, emit iff conf ≥ `_EQUIP_CONF_MIN`". Accepts a small false-record risk on a truly-naked engine
(rare; only Koleda-like agents) pending the empty reference. Discs keep the H19 path for now (no skip
manifested this run).

**Also found:** `_log.*` (slot_empty / slot_reclick / tab_gate_fail …) never reach `scan.log` — it tees
stdout only, so every diagnostic marker from the live run was invisible (0 matches). The logger must be routed
to the run dir, else live debugging stays blind (H21.3). This is why the engine skips left no log trace.

### D36 UPDATE — references received (ref_18/19); OQ-H21a ANSWERED, signal corrected

User supplied `reference_18_unequipped_disc_slot_clicked.png` and `reference_19_unequipped_engine_clicked.png`
(`screenshots/`). They **refute the "blank center pane" assumption** and confirm the H18 corruption bug is
real: clicking an empty slot **auto-selects inventory[0]** and renders its full detail center — ref_18 shows
"Shockstar Disco [1]" Lv 15/15 + substats; ref_19 shows "Hellfire Gears" Lv 60/60. So **title/level parse is
NOT a valid equipped signal** (it populates for empty slots too) — a naive post-click parse would assign the
first inventory item as this agent's gear.

**Corrected discriminator — the bottom ACTION-BAR.** Equipped slot → leftmost button **"Unequip All"** (disc)
/ "Unequip" (engine); empty slot → **"Equip All"/"Equip"**. Verified with the project recognizer:

| frame | state | action-bar OCR | `"unequip" in text` |
|---|---|---|---|
| ref_8 | equipped disc | `Unequip All` | True ✓ |
| ref_18 | empty disc | `Equip All` | False ✓ |
| ref_19 | empty engine | `Equip` (right-shifted) | False ✓ |

Signal: **`equipped = "unequip" in ocr(action_bar).lower()`** — art-independent, OCR-confirmable, one rule for
disc + engine, empty never contains "unequip". Use a bbox (or full-bar OCR, x≈1100–1750 y≈1002–1052 ref) wide
enough to span BOTH the disc "Unequip All" (x≈1140–1310) and the right-shifted engine "Unequip" (x≈1380–1520);
the narrow x1120–1360 bbox reads the disc fine but misses the engine's button position.

**Net design change:** the pre-click `_disc_slot_equipped`/`_engine_slot_equipped` heuristics are retired as
gates. Per slot: click → `_slot_panel_rendered` → action-bar OCR. If "unequip" → parse center, emit record;
else empty → no record, no corruption. We never click "Equip" (no accidental equip; anti-ban unaffected — same
synthetic click + Escape). Residual: an EQUIPPED-engine select frame is unconfirmed (we have empty-engine
ref_19 only) — verify the engine "Unequip" position live (low risk; same button system as the disc).

---

## D37 — Owned/unowned detection: level + level-up chevron, NOT render hue (H22)

**Author:** Opus 4.8 · **Date:** 2026-06-08 · **Supersedes:** H15 render-hue ownership test.

**Symptom (live H21.4 run).** `scan-all --agents-only` silently skipped OWNED agents — Harumasa
(after Billy), and Lycaon + Komano Manato (after Soldier 11). The new file-routed log
(`archive/live_20260605/agent_scan.log`, D36/H21.1) showed them hitting the `agent_skip — unowned
agent` path at consecutive strip positions (8+9, 28+29) — they were *classified unowned*, never
opened. The user's framing was "agent switching"; the actual fault was the ownership gate.

**Root cause — the H15 premise is false.** H15 assumed ZZZ renders unowned agents as a blue
DUOTONE (monochrome, low hue spread) and keyed ownership on hue diversity of the character render.
The live unowned frame (`nav_first_unowned.png`, "Hugo Vlad") is rendered in **full colour** — a
blonde man in a blue suit; his `blue_frac=0.93` is the *suit*, not a duotone. Measured across the
33 live owned captures, owned monochrome/ice agents collide with the unowned cluster with **no
margin**:

| agent | blue_frac | hue_std | H15 verdict |
|---|---|---|---|
| unowned Hugo | 0.93 | 24 | grayed ✓ |
| owned agent_008 | 0.87 | 27 | grayed ✗ (false) |
| owned agent_014 | 0.75 | 29 | grayed ✗ (false) |

The render hue is **not separable**; the verdict flickered with the idle-animation frame, so
monochrome owned agents (Lycaon = ice/white) were dropped intermittently. The footer "Fully
Equipped" pill also fails (owned-but-unequipped agents read identical to unowned). **No single
base-page pixel region separates owned from unowned.**

**Reliable signal (user-confirmed in-game, validated on all 34 live frames).** Two parts:
1. **Level ≥ 2 ⇒ OWNED.** An agent above Lv.1 cannot be unowned. This fast-path covers every built
   agent — including maxed ones (level-up pill shows gray "MAX") and, critically, owned agents at an
   ascension breakpoint (e.g. agent_023 at Lv.50/50) whose `>>` pill is **WHITE**. Their white pill
   is therefore never mistaken for unowned.
2. **At Lv.1 (or unreadable level), the level-up `>>` chevron decides.** It is an animated **GREEN**
   on owned agents (shades of green, never white) and a static **WHITE** on unowned. On the live
   frames green/white separate cleanly (green≈0.16, white≈0.16, each ≈0 on the other class) in the
   pill bbox `(1315,455,1370,535)`. Live OCR reads **blank** on the unowned "Lv. 01" pill (→ level
   0), which is folded in with Lv.1 → consult the chevron.

The chevron alone is NOT ownership (agent_023, owned, also shows white) — it is only consulted once
level is confirmed < 2.

**Decision.** Replace `_is_owned_agent` (render hue) with:
- `_chevron_color_fracs(frame, calib)` — pure pixel op returning (green_frac, white_frac) of the
  `>>` pill.
- `_classify_owned(level, green, white)` — pure rule: `level>=2 → owned`; else `green→owned`,
  `white→unowned`, `neither→owned`.
- `AgentNavigator._agent_owned(base_frame)` — OCRs the level (`_LEVEL_BBOX`), then `_classify_owned`.

`scan()` now captures the **Base tab first** (it carries both the level pill and the chevron; it is
the only tab where ownership is readable), decides ownership there, and only then pays for
Skills/Equipment. An unowned agent costs one Base frame, not a 7-slot equipment walk.

**Failure-direction principle.** Every ambiguity (blank level + no clear chevron) returns OWNED.
Dropping an owned agent is the cardinal sin (data loss); an extra unowned capture is filterable
noise. This also protects white-pill breakpoint agents (agent_023) if their level OCR ever fails:
they fall to the chevron only when level<2, and the bias is toward capture.

**Traversal unchanged (deliberately).** We still SKIP-don't-STOP unowned agents and stop on
ring-close. The user noted the roster is sorted owned-first and "we can stop at the first unowned,"
but entry lands on an *arbitrary* strip position, so an early-out could orphan the owned agents
*before* the entry point. Skip-don't-stop + ring-close is complete regardless of entry/sort, and on
a sorted roster the unowned tail is still traversed only once (cheaply).

**Rejected alternatives.** (a) Retune the hue thresholds — impossible, clusters overlap. (b) Footer
"Fully Equipped" pill — collides with owned-but-unequipped agents (agent_011/025/032 read ≈0, same
as unowned). (c) Equipment-tab availability oracle — `nav_equip_unavailable.png` shows a
fully-equipped owned agent was already false-dropped as "trial", so that gate has its own
false-positive (logged as OQ-H22a). (d) Stop at first unowned — unsafe under arbitrary entry.

**Open questions / latent risk.**
- **OQ-H22a:** `_EQUIP_UNAVAILABLE` (equip-tab-rendered gate) false-positived on a fully-equipped
  owned agent (`nav_equip_unavailable.png`) — a *second*, independent silent data-loss path. It did
  NOT fire in the H21.4 run (no `agent_skip_trial` lines), so it is lower priority, but it should be
  hardened (likely a render-settle/timing fix) before the next full scan. Tracked as a TASK.
- **OQ-H22b:** the chevron bbox and green/white thresholds were calibrated at 1920×1080 (scale 1.0).
  Confirm they hold at other capture resolutions, or scale them via calib like other bboxes (they
  already pass through `_crop`, which scales — only the fractions are resolution-independent).

---

## D38 — Decommission Rust packet-sniffer (2026-06-10)

**Context**: The original `youkai/` Rust app was a packet-sniffer prototype targeting the ZZZ
KCP/MHY protocol. It was stopped at C0 (cipher blocked) in favour of the OCR approach (D-N-OCR).
The Rust code is no longer built or maintained.

**Choice**: Leave the `youkai/` subdirectory in place (no active build dependency, no ongoing
maintenance), document it as decommissioned in README.md. Retain `youkai/src/zod.rs` as a
field-name reference for the ZOD schema. The `irminsul/` subdirectory is an unmodified reference
clone and is also left untouched.

**Rationale**: Deleting source history offers no benefit — the code is already inert (not in the
Python build path). Keeping `zod.rs` avoids re-deriving the camelCase ZOD field name rules. A
README note is sufficient to prevent future contributors from confusing the dead Rust app with the
active OCR tool.

**Rejected**: Hard-deleting `youkai/src/` — would lose `zod.rs` schema reference and obscure the
project's history without any practical benefit.

---

## D39 — GUI frontend: revive Rust egui shell over a subprocess JSONL protocol (2026-06-11)

**Context**: scan-all (Python CLI) is validated for v0.1. The draft GUI is the egui
"hacker console" in `youkai/`, still wired to the decommissioned packet-sniffer backend
(D38): pktmon monitor, fake packet counters, irminsul update checker, admin elevation.

**Choice** (amends D38): the `youkai/` crate returns to the active build path as a
**GUI shell only**. All sniffer machinery is deleted (monitor/capture/wish/update/good/
player_data, pcap deps, admin elevation); `zod.rs` stays as schema reference. The GUI
spawns `youkai-ocr scan-all --porcelain` as a child process and renders a versioned
JSONL event stream (run_start/phase_start/progress/phase_done/warning/done/error).
Scan-mode config (Full vs Discs-only) maps to a new generic `--phases` flag
(subsumes `--agents-only`). Porcelain implies non-interactive: `input()` prompts become
`warning` events. The GUI minimizes itself during the scan — dxcam region capture would
otherwise include GUI pixels overlapping the game window (correctness, not polish).

**Rationale**: subprocess boundary gives crash isolation, a trivially correct KILL
(process termination; run dir stays resumable), independent release cadence, and reuses
the polished console design instead of rewriting it. The protocol is the stable seam:
future frontends reuse it without touching scan logic.

**Rejected**: (a) Python GUI rewrite — discards a finished design to remove one process
boundary that is actually a feature. (b) PyO3 embedding — packaging pain, GIL vs egui
threads, no crash isolation. (c) Rust port of the scanner — re-validating weeks of OCR
heuristic tuning for no v0.1 benefit. (d) Keeping the old ExportSettings min-level
filters — sniffer-era leftovers; the scanner exports everything, filtering is a
non-goal for v0.1.

**Plan**: BRIEF_gui.md / DESIGN_gui.md / TASKS_gui.md (T1–T13).

---

## D40 — Portable onedir distribution; tesseract bundled as a sibling binary (2026-06-11, Opus 4.8 Planner)

**Context**: User requirement escalated mid-build: the tool must "run just from the exe"
on a machine with no dev Python env. This promotes T13 (PyInstaller packaging) from a
v0.1 stretch/non-goal to a hard requirement, and amends BRIEF_gui.md non-goal #3.

**The forcing constraint**: `pytesseract` is a thin wrapper that shells out to an external
`tesseract.exe` (Apache-2.0; redistributable) with its own `tessdata/*.traineddata`.
PyInstaller bundles the Python deps (opencv-headless, dxcam, pynput, rapidfuzz, pywin32,
Pillow) but **cannot** absorb tesseract — it is not a Python package. Therefore a single
literal `.exe` is not cleanly achievable; tesseract must ride along as a bundled native
binary the scanner points `pytesseract.tesseract_cmd` at.

**Choice**: ship a **portable onedir folder** (AdeptiScanner model), not onefile.
```
youkai-portable/
  youkai.exe          (Rust egui GUI)
  youkai-ocr.exe      (PyInstaller --onedir scanner)
  _internal/          (CPython + opencv/dxcam/... native deps)
  tesseract/
    tesseract.exe
    tessdata/eng.traineddata
  export/
```
- **onedir over onefile**: onefile temp-extracts a heavy native payload (opencv + dxcam
  DLLs) to `%TEMP%` on every launch — slow startup and a magnet for AV false positives —
  and gains nothing here, since tesseract ships as an external folder regardless. onedir
  starts fast and the folder *is* the unit of distribution.
- **Sibling discovery needs no Rust change**: `scan.rs::resolve_command` slot 2 already
  looks for `youkai-ocr.exe` beside the GUI exe. Co-locating both in the folder root makes
  the GUI find the scanner with zero code change.
- **Bundled-tesseract resolution (the one Python change)**: extend
  `TesseractRecognizer.__init__` (recognize.py) with a third lookup ahead of PATH and the
  hardcoded Program Files path: a `tesseract/tesseract.exe` resolved relative to the
  frozen-app root (`sys._MEIPASS` when frozen, else exe/cwd dir), and set `TESSDATA_PREFIX`
  to the bundled `tessdata/`. Falls back to existing behavior in dev (WSL `python -m`).
- **Dev mode unchanged**: slot 3 (`python -m youkai_ocr`) and WSL testing are untouched;
  packaging is purely the Windows release path. The PyInstaller build runs on Windows
  (no cross-compile from WSL), consistent with the existing "release exe built on Windows"
  rule in TASKS_gui.md.

**Rationale**: the only redistribution-blocking dependency is tesseract, and the cleanest
honest answer to "external native binary" is "ship it beside the exe and point at it,"
not "fight PyInstaller to fake a single file." onedir keeps startup fast and AV calm; the
folder-as-unit matches what the sibling-exe discovery was already designed for.

**Rejected**: (a) onefile per tool — slower temp-extraction, worse AV posture, tesseract
still external anyway. (b) Embedding tesseract as onefile data extracted to temp —
fragile path/temp resolution, heaviest AV risk, no real "single exe" win. (c) Requiring
users to install Tesseract-OCR separately — defeats "portable," and the current Program
Files auto-detect already covers the dev-with-installer case.

**Plan delta**: TASKS_gui.md T13 is expanded into T13a (bundled-tesseract resolver,
Python, testable in WSL) + T13b (PyInstaller onedir spec for youkai-ocr.exe) + T13c
(assemble portable folder + clean-machine validation, Windows). BRIEF non-goal #3 amended.

---

## D41 — Frozen-exe build must be local-path + version-stamped (resolves T13c ImportError escalation)

**Date:** 2026-06-12 (Planner/Opus, escalation resolution)

**Context.** T13c repeatedly produced a frozen `youkai-ocr.exe` that crashed in
`_cmd_scan_all` with `ImportError: attempted relative import with no known parent package`,
even after (a) converting all `cli.py` imports to absolute, (b) adding `packaging/run.py`
as the entry, and (c) 6+ `--clean` rebuilds. Worker escalated suspecting UNC/pyc caching.

**Diagnosis (confirmed — the traceback is only self-consistent one way).** The crashing exe
is a **stale artifact built from pre-fix source**, not the output of the current spec. Proof,
three independent facts that all contradict current source/spec:
1. Bootloader `Failed to execute script 'cli'` → the Analysis entry was `cli.py`, but the
   current spec entry is `packaging/run.py` (would say `'run'`).
2. `File "cli.py", line 1319, in <module>` → cli.py ran as `__main__` (its last line, 1319,
   is `main()`); the current spec never runs cli.py as a top-level script.
3. The relative-import error fires at `cli.py:849`, where **current** source is
   `from youkai_ocr.capture import calibrate_window` (absolute). Only old source
   (`from .capture …`) throws there. sed preserves line numbers, so 849/1319 still align.

The current source + spec **cannot** produce this traceback. The fresh PyInstaller output is
not what's being launched. Most likely the launched binary is the assembled
`youkai-portable\youkai-ocr\youkai-ocr.exe` (assembled once, pre-run.py) while rebuilds land
in `dist\`; or PyInstaller, reading source over the `\\wsl$` UNC mount, bundled a cached
`cli.pyc`. The code is already correct — this is purely a stale-artifact problem.

**Decision.**
1. **Build on a local Windows path, never over UNC.** New `packaging/build_local.ps1`
   robocopy-mirrors the repo to `C:\Temp\youkai-build\` (`/MIR` so dist/build/portable
   leftovers are purged), runs `python -m PyInstaller packaging\youkai-ocr.spec --clean -y`
   there, runs `assemble.ps1` there, then copies `youkai-portable\` back to the repo. Kills
   the UNC mtime/pyc-cache class of bug outright.
2. **Stamp a build id and gate on it.** Add `__version__` to `youkai_ocr/__init__.py`, wire a
   `--version` action into the cli argparse, and have `build_local.ps1` assert the freshly
   built exe prints the expected id **before** assembling. This makes "am I running the new
   binary?" answerable in one command — a stale exe can never again pass silently. (Note
   `--help` is *not* a sufficient gate: the broken import is deferred inside `_cmd_scan_all`,
   so the stale exe's `--help` exits 0.)
3. **Keep run.py entry + absolute imports** as defense-in-depth: either alone makes the exe
   robust even if cli is run as `__main__`. Belt and suspenders, no reason to remove.

**Rejected.** Continuing to debug imports (already correct — wastes cycles); building over UNC
with more cache-clearing incantations (fragile, non-reproducible); onefile (orthogonal, see D40).
