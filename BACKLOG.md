# Backlog

A holding area for ideas that aren't ready to be tracked GitHub issues yet. Either too early (investigation needed before scoping is honest), or contingent on something else (demand, an external decision).

Promote an entry to a GitHub issue once it's concrete enough that the issue body would be useful rather than aspirational.

---

## Boss Katana MkII support

**Status:** investigation needed
**Why here, not as an issue:** scope is unknown until we see Katana's patch file format. Also contingent — only matters if a Katana-owning user is actually going to use it.

**Why it's interesting:**
- Author's friend has a Katana MkII, no ME-80. Building this would let the tool serve both.
- Same ecosystem (BOSS / BOSS TONE STUDIO), likely similar workflow (export `.tsl`-ish file → import into the Katana app → push to amp).

**What we don't know yet:**
- The Katana exports patches via BOSS TONE STUDIO for Katana (different app from the ME-80 one). Patch file extension? Same `.tsl` or different?
- JSON shape — same top-level / params split, or different schema?
- Amp / effect enum set — almost certainly different. Katana has its own 5 amp characters with variations, different effect categories, more parameters per effect.

**30-minute investigation to do before promoting to an issue:**
1. Find a sample exported Katana patch file (community parsers / GitHub / a Katana owner)
2. Skim the file format — is it JSON? Is it readable? Is there a community parser?
3. Estimate how much of our existing code transfers vs. needs a separate writer

**If the investigation says "go":**
- This becomes a refactor + new-writer project. Factor out the device-specific code (schema, enums, defaults, writer) so the LLM layer, recipe matcher, CLI, and web UI route to either device. Probably 2–3 sessions of work.
- Will also need a Katana-specific recipe set (the recipes are amp-palette-aware; ME-80's recipes don't transfer).

**If the investigation says "skip":**
- Note here why, move on. Door stays open if his friend gets vocal about wanting it.

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
