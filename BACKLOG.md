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
