# Backlog

A holding area for ideas that aren't ready to be tracked GitHub issues yet. Either too early (investigation needed before scoping is honest), or contingent on something else (demand, an external decision).

Promote an entry to a GitHub issue once it's concrete enough that the issue body would be useful rather than aspirational.

---

## Boss Katana MkII support

**Status:** ready to promote to issue, contingent on friend's actual demand
**Investigation done:** 2026-06-27

**Why it's interesting:**
- Author's friend has a Katana MkII, no ME-80. Building this would let the tool serve both.
- Same ecosystem (BOSS / BOSS TONE STUDIO), similar workflow (export `.tsl` → import into Boss Tone Studio for Katana → push to amp).

### Investigation findings

**Format:** Yes, also `.tsl`, also JSON. Parses with `json.load(f)`. But the schema is **substantially different** from ME-80's — this is not a small extension, it's a parallel implementation.

| | ME-80 | Katana MkII |
|---|---|---|
| Top-level shape | `{device, patchList, liveSetData, version}` | `{name, formatRev, device, data}` (data is a nested list-of-lists) |
| Patch shape | `{params: {82 flat keys}, orderNumber, id, name, ...}` | `{memo, paramSet: {22 keys}}` |
| Value encoding | Decimal strings (`"50"`) | **Hex byte strings (`"4B"`)** — arrays of bytes per param |
| Patch name | `name1..name16` (decimal ASCII codes) | `UserPatch%PatchName` array of hex ASCII codes |
| Amp palette | 9 types | 28 ("sneaky amp") types |
| Effect structure | 8 fixed blocks in fixed signal chain | Multi-block per category: `Fx(1)`, `Fx(2)`, `Delay(1)`, `Delay(2)`, `Contour(1)`, `Contour(2)`, plus three `Patch_N` packed blocks |
| Assignment matrices | Single `ctl_target` bitmap | Per-knob, per-expression-pedal, per-footswitch (`KnobAsgn`, `ExpPedalAsgn`, `GafcExp1Asgn`, `FsAsgn`) |

**Reference implementations found:**
- [`mathieu-lemay/katana-tsl-parser`](https://github.com/mathieu-lemay/katana-tsl-parser) — Python read/write library for Katana TSL. **No LICENSE** (same trap as `johnsrude/BossToneStudio` — can't redistribute their `default.tsl`, but the format is reverse-engineerable from a personally-exported file).
- [`leon3110l/katana_tsl_patch`](https://github.com/leon3110l/katana_tsl_patch) — older, author admits "code isn't great."
- [`leon3110l/rs2tsl`](https://github.com/leon3110l/rs2tsl) — Rocksmith → Katana TSL converter. Precedent for tone-text → Katana TSL pipelines.
- [`mathieu-lemay/katana-mk2-patches`](https://github.com/mathieu-lemay/katana-mk2-patches) — sample patches in the wild.
- Format documentation: [mylespaul.com forum thread on the 28 sneaky amp types](https://www.mylespaul.com/threads/boss-katanas-28-sneaky-amp-types.392118/) cited by the parser.

**Adjacent project:** [`ArthurVaiselbuh/KatanaToneStream`](https://github.com/ArthurVaiselbuh/KatanaToneStream) — **MIT licensed**, created the same day as our project (2026-06-27), description "Push tones directly to the katana mk2 by song / artist name." Literally the same concept, parallel implementation. Worth watching / considering collaboration vs. independent development.

### What building Katana support actually requires

It's a real project, not a flag. To do it well:

1. **Refactor the core to be device-pluggable** (~1.5 sessions):
   - Introduce a `Device` abstraction with `enums`, `schema`, `defaults`, `writer`, `renderer` methods
   - Existing ME-80 implementation becomes the first concrete device
   - LLM layer, recipe matcher, CLI, and web UI become device-agnostic
   - Tests get a device fixture
2. **Build Katana device implementation** (~1.5 sessions):
   - `katana_enums.py` — 28 amp types + Katana FX/Delay/Contour categories
   - `katana_schema.py` — multi-FX, multi-Delay, packed-Patch_N shape
   - `katana_writer.py` — hex-byte-array encoding, nested `data[[]]` envelope
   - `katana_defaults.py` — full default `paramSet` template
   - `katana_renderer.py` — display (Katana's chain is non-linear, harder to render than ME-80's)
3. **Curate Katana-specific recipes** (~0.5–1 session):
   - ME-80 recipes don't transfer (different amp palette, different effect parameters)
   - Smaller initial set acceptable (~10–15 recipes) since the friend isn't running 200 songs
4. **CLI / web device selection** (~0.5 session):
   - `tone-gen --device katana "..."`, web UI device picker
   - Recipe matcher routes to device-specific recipe book

**Total: 4–4.5 sessions of focused work.**

### Decision point

Promote to an issue when:
- The friend confirms they would actually use it (not "would be cool" — "I'll load my pedal with patches from this"), AND
- Author is willing to commit 4+ sessions to it

Skip if:
- Friend's interest is theoretical, OR
- The MIT-licensed `KatanaToneStream` project ships first and serves the need

Door stays open either way; this investigation makes the issue ready to write the day the demand is real.

---

## Direct USB MIDI to the ME-80 (eliminate the BTS-Import step)

**Status:** investigation done 2026-06-27 — verdict: **skip indefinitely**
**Why here, not as an issue:** the ME-80 has no documented SysEx parameter-write path (spec §1). Reverse-engineering may or may not be tractable; we won't know until we look.

**Why it's interesting:**
- Inspired by [`ArthurVaiselbuh/KatanaToneStream`](https://github.com/ArthurVaiselbuh/KatanaToneStream), which writes directly to a Katana via reverse-engineered Roland DT1 SysEx. They eliminated the BTS import step entirely — generate, hear instantly.
- Today our pipeline ends at "open BTS, Import, drag onto slot." Three GUI steps in a third-party Intel-binary app (BTS isn't Apple-Silicon native), a real failure-point dependency.
- The bigger value isn't shaving 30 seconds off gig prep — it's enabling a real iterative tweak loop ("generate, hear, tweak, hear again") that the file-roundtrip currently makes tedious.

**What we don't know:**
- Whether the BTS-to-pedal USB protocol for ME-80 is reverse-engineerable like Katana's was
- Whether it allows fine-grained parameter writes (Katana-style) OR is bulk-upload only
- Whether it's standard Roland SysEx, proprietary binary, or obfuscated

**Three possible outcomes:**

1. **Fine-grained protocol** (Katana-style) → ~2-3 sessions to build, big UX win, eliminates BTS dependency entirely
2. **Bulk-upload only** → ~1 session to build, modest UX win (skip the drag), still removes BTS from the path
3. **Encrypted / opaque** → drop the idea, BTS Import stays the path

**Investigation plan:**

Phase 1 — research-only (no hardware): scan public reverse-engineering work, GitHub repos that talk to ME-80 over USB, forum threads, Roland-published MIDI implementation guides. If anyone's already documented this, we know which bucket we're in without sniffing.

Phase 2 — live USB capture (needs hardware connected): if phase 1 is inconclusive, capture USB traffic while BTS imports a liveset using `PacketLogger` (macOS) or `usbmon` + Wireshark (Linux). Decode the bytes against the MIDI / Roland DT1 standards. ~1-2 hours of interactive work with the author.

### Phase 1 findings (2026-06-27)

**The protocol path is closed enough not to pursue.**

Evidence:

1. **BOSS ME-80 Training Guide** (cdn.roland.com/assets/media/pdf/ME-80_Training_Guide.pdf), page on USB usage: *"It can even respond to MIDI program and control changes via USB."* No mention of SysEx, parameter writes, or bulk dumps. The documented MIDI surface is PC + CC only.
2. **Zero open-source reverse-engineering** of the ME-80 USB protocol on GitHub. Searched "boss me-80 midi", "boss me-80", and code search for "me-80" + "sysex" — only false-positive hits and our own repo. In ~12 years since the pedal shipped, no one has built a public MIDI-direct tool for ME-80.
3. **Roland published DT1 SysEx for Katana but NOT for ME-80.** This is why KatanaToneStream's approach works for Katana — the protocol is documented in the Katana MIDI implementation chart. The ME-80's MIDI implementation chart documents PC + CC only.
4. **BTS clearly uses a proprietary USB Bulk-endpoint protocol** for patch upload, not standard MIDI. Reverse-engineerable in principle, but no one's published the work.

### Three outcomes mapped to ME-80 reality

- **Fine-grained protocol** (Katana-style): **very unlikely** — the pedal doesn't expose SysEx parameter messages at all
- **Bulk-upload only**: possible, would require 1-3 hours USB sniffing + decoding + ~1 session implementation
- **Opaque**: possible — the protocol may be sufficiently custom that decoding it isn't worth the effort

### Honest cost/benefit if we pursued bucket #2 (bulk-upload)

- Time saved per gig prep: ~20-30 seconds (skip the drag-to-slot)
- BTS dependency removed: real win on Apple Silicon where BTS runs via Rosetta
- **Iterative tweak loop: NOT unlocked** — still upload-whole-patch, no real-time parameter feedback. The thing that made direct USB attractive on Katana doesn't apply here.
- Bricking risk: sending malformed bulk messages could corrupt a user memory slot
- Total cost: 4-5 hours of work for a small, bounded UX gain

### Verdict

Skip indefinitely. The killer point is that **the real value of direct USB (live iterative tweak loop) requires the fine-grained protocol the ME-80 does not expose.** Bulk-upload-only direct USB is just "skip a drag-and-drop step" — small UX gain, non-trivial implementation, real bricking risk.

Better uses of the time: #7 / #9 / #10 (tone accuracy work) and #5 (setlist generation). Once #5 lands, the BTS Import step happens once per gig prep — a 30-second cost, not iterative pain.

### Revisit only if

- A user (not us) publishes a reverse-engineered ME-80 USB protocol on GitHub, OR
- BTS breaks on a future macOS update and we genuinely lose the import path, OR
- Roland releases an updated MIDI implementation chart documenting SysEx for ME-80 (unlikely after 12+ years)

---

## Apple Music playlist integration (for the setlist feature, see `#5`)

**Status:** deferred indefinitely
**Why here:** Apple Music's API requires a paid Apple Developer account ($99/year). The setlist feature already supports plain text, CSV, and Spotify — Apple Music is a "nice to have" that hits a real-money cost.

**Promote to an issue when:**
- Author has an Apple Developer account for an unrelated reason, OR
- A user specifically requests it and it's worth the cost.

---

## Custom tone-knowledge fine-tuned model (for tone accuracy, see `#6`)

**Status:** research-grade, deferred indefinitely
**Why here:** Mentioned during the tone-accuracy brainstorm as the "ultimate" knowledge lever. Would mean building a dataset of (song, artist, year, gear, ME-80 settings) tuples and fine-tuning a smaller model to specialise on guitar tone — would likely outperform a generic 14B model at this specific task.

**Why deferred:**
- Dataset construction is the real work, and it's substantial (probably 500-1000+ high-quality examples)
- A fine-tune of a 7B model on a Mac is ~half a day of compute
- The marginal accuracy gain vs. `#7` (curated recipes) + `#10` (gear lookup) + `#11` (refinement) is unclear and probably small
- Maintenance burden: every time the underlying model improves, the fine-tune has to be redone

**Promote to an issue when:**
- All of `#7`, `#10`, and `#11` are landed and demonstrably not enough, OR
- Author finds the dataset construction genuinely fun (it sort of is — it's curating opinionated tone knowledge), OR
- Someone with ML pipeline experience wants to drive it.

---

## Adding entries

Format per entry:

```markdown
## <thing>

**Status:** <investigating | deferred | contingent | researching>
**Why here, not as an issue:** <reason>

<context, links, what we know, what we don't, what would trigger promotion to an issue>
```

Keep entries short. If it grows past ~half a page of dense detail, it's probably ready to be a real issue.
