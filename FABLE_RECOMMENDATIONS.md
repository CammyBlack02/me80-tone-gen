# Repo review and recommendations

A full-codebase review of me80-tone-gen (source, tests, recipes, backlog, and issues #1–#13), with recommendations ordered by impact. Items marked **[landed on this branch]** were implemented alongside this document; the rest are recommendations with enough detail to act on later.

The one-paragraph verdict: the architecture is genuinely good — the core-module pattern is real (not aspirational), the hardware-verified invariants are the right kind of paranoia, and the no-defaults schema decision is a sharp piece of LLM engineering. The highest-leverage improvements were not architectural: a live recipe-matcher bug, the model setting generic knobs blind, and accuracy work having no measurement.

---

## 1. Recipe matcher false positives **[landed on this branch]**

Bare substring matching over 102 recipes misfired on ordinary descriptions, reproduced against the shipped `recipes.json`:

| Description | Matched |
|---|---|
| "warm evening clean tone" | nine-inch-nails-distorted (`nin` inside "eve**nin**g") |
| "gentle morning acoustic vibe" | nine-inch-nails-distorted (`nin` inside "mor**nin**g") |
| "a tone that would suit soft jazz" | alice-in-chains-rhythm (the alias `would`) |
| "creepy ambient horror tone" | radiohead-paranoid-android (`creep` inside "creepy") |
| "come alive stadium rock" | pearl-jam-rhythm (`alive`) |

Because the prompt tells the model not to deviate from a matched recipe's anchor, a false positive actively overrides the user's description — a gentle morning acoustic request was being seeded with industrial distortion.

Fixed by matching aliases at word boundaries (lookarounds, so "ac/dc" and "b.b. king" still anchor) and removing the three aliases that are ordinary standalone English words (`would`, `alive`, `plush` — their recipes stay reachable via artist/song aliases). Regression tests pin the embedded-word cases, a set of innocent generic descriptions, and cross-recipe alias uniqueness.

**Still recommended:** when adding recipes, treat single-common-word aliases (`journey`, `muse`, `cream`, `creep`, `boston`) as a smell. Word boundaries protect against embedded matches, but a description legitimately containing the bare word will still route to the artist. The innocent-descriptions test is the place to encode any future report of a wrong routing.

## 2. Per-type knob semantics **[landed on this branch]**

The biggest accuracy lever not already on the roadmap. The generic slots (`comp1..3`, `mod1..3`, `fx2_1..4`) mean different things per type — CHORUS knob1 is RATE, HARMONIST knob1 is KEY, COMP knob1 is SUSTAIN — but neither the JSON schema, the prompt, nor the rendered knob list said so. The model was choosing values for knobs whose meaning it could not see (and the human dial-in card printed "knob1 40"). This plausibly explains why supporting-effect values felt mushier than preamp values, whose fields have real names.

Landed: per-type knob-label tables in `enums.py`, consumed in three places so they can never drift apart — JSON-schema field descriptions on the generic knobs (where structured-output models read them), a generated reference block in `SYSTEM_PROMPT` plus a delay TIME→milliseconds mapping note, and real labels on the renderer's card.

**Action needed from the author (10 minutes with the spec/manual):** labels were only added for types where standard BOSS parameter names are unambiguous. These types deliberately fall back to generic `knob N` and should be filled in from spec §3.3 / the owner's manual parameter chart, then added to the tables in `enums.py`:

- COMP/FX1: OCTAVE, Single>Hum, Hum>Single, SOLO
- MOD: VIBRATO, OVERTONE
- EQ/FX2: everything except EQ (PHASER, TREMOLO, BOOST, DELAY, CHORUS — four knobs each)

A wrong label would be worse than none (the model would confidently set a "level" that is actually a rise-time), which is why they were omitted rather than guessed.

## 3. Eval harness — make accuracy work measurable **[landed on this branch]**

Issue #6's remaining levers (#10 gear lookup, #11 refinement, #13 preference learning) and any prompt iteration were being judged by ad-hoc A/B listening (#4's acceptance was "3 of 5 look better"). That can't catch regressions and doesn't scale.

Landed: `evals/cases.json` (structural, guitarist-agreeable assertions — "djent leaves delay off", "surf uses SPRING", coarse knob bounds, never exact values) plus `scripts/run_eval.py`, which runs each case N times against real Ollama and reports per-assertion pass-rates, with `--out` snapshots for before/after diffs, `--no-recipes` to isolate the raw prompt, and `--model` to compare models. Unit tests keep the cases file from rotting (paths must resolve against `SemanticPatch`).

**Recommended workflow:** before any prompt/recipe/model change, `run_eval.py --out before.json`; after, diff. Grow the case set whenever a bad generation is noticed in real use — that's a free regression test. When the eval is trusted, trying alternative models becomes a ten-minute experiment.

## 4. Friendly failure modes **[landed on this branch]**

- Ollama not running / model not pulled — the two most common real-world failures — produced raw tracebacks (`cli.py` only caught `GenerationError`). Now translated to actionable one-liners ("is it running?", "ollama pull <model>") in both CLI and web; unrecognized exceptions still propagate raw.
- `--temp` with `--variants > 1` was silently ignored (variants use their own spread). Now a usage error pointing at `--temperatures`.
- Usage errors exited 1 in two paths despite the documented contract being 2. Fixed.
- `--json` with `--variants` emitted a bare shape with no liveset or recipe info, inconsistent with everything else. It now emits the same envelope as the web API's `/api/generate`. Single/batch `--json` still prints the liveset itself on purpose — that output doubles as valid `.tsl` content (`tone-gen --json > x.tsl` works).
- `patch_name` had no charset constraint; the model could emit "CAFÉ" and push ASCII code 201 into the export. Schema now constrains to printable ASCII (a bad name becomes a validation retry), and `encode_name` sanitizes defensively.
- `tone-gen-serve` is installed even without the `web` extra and died with an ImportError traceback. It now prints the `pip install 'me80-tone-gen[web]'` instruction (entry point moved to an import-light `serve.py`).

## 5. CI + lint **[landed on this branch]**

"pytest must pass on main at all times" was policy enforced by memory. Now `.github/workflows/ci.yml` runs ruff + pytest on Python 3.11–3.13 for every push/PR (the Contra_1.tsl conformance tests already skip cleanly without the non-redistributable reference file). Ruff config is minimal (`E,F,W,I,B,UP`, line length 100); its findings on the existing code were small and are fixed.

**Recommended next:** mypy would be nearly free — the codebase is already fully annotated. The `client: object | None` parameter in `generator.py` would be cleaner as a small `Protocol` with a typed `chat` method; do that when adding mypy.

---

## Recommendations not implemented here

### 6. Roadmap re-ranking (opinion)

With Spotify (#9) dead upstream, build **#2 (library + tweak mode) before #10 (gear lookup)**. Three issues stack on #2's plumbing — #5 setlist (the killer use case), #11 refinement chat, #13 preference learning — and it has zero external dependencies, whereas #10 hinges on scraping-permission questions outside the project's control. The knob-semantics work in §2 also amplifies #11 specifically: a refinement chat where the model knows knob1 is RATE can actually execute "slow the chorus down".

### 7. Packaging and adoption

- **Publish to PyPI** (PolyForm Noncommercial does not prevent it). `pipx install me80-tone-gen` is a step-change in accessibility for guitarists who are not Python people. The pyproject is already publish-ready; it needs an account, a token, and optionally a `release.yml` workflow on tags.
- **Version discipline:** the version has sat at 0.1.0 through recipes 8→102, few-shot prompt, and variants. Bump on each merged feature and keep a two-line-per-release CHANGELOG; it makes "what changed since I last pulled?" answerable.
- **README demo GIF** of the web UI near the top. The CLI transcript is good; a 10-second visual of description → patch → download is better for the drive-by audience.
- Consider `--port`/`--host` flags (or env vars) on `tone-gen-serve`; 8765 is hardcoded.

### 8. Web health preflight

`/api/health` returns `{"status": "ok"}` even when Ollama is down; the user finds out after typing a paragraph and waiting. Make it (or a `/api/ready` endpoint the UI pings on load) check Ollama reachability and whether the configured model is pulled, and have the UI show a banner with the fix command. Small, self-contained, good first issue.

### 9. Recipe hygiene at 100+ entries

- The `confidence` field exists but no packaged recipe sets it — all 102 default to `untested`, including the 8 originals that predate the field and may have been ear-tested. Marking the tested ones (per issue #7's acceptance: ≥30) also lets the UI/CLI surface "Recipe matched: master-of-puppets-rhythm (untested)" so users calibrate trust.
- A recipe's `patch` should round-trip through `semantic_to_params` in a test so a typo'd type name in JSON fails in CI, not in a user's session. (The Pydantic schema already catches most of this; the enum-index lookup is the remaining gap.)
- When #13 (preference learning) lands, per-recipe deltas are also the signal for *recipe* fixes: if every user drops MoP's gain by 10, the recipe is wrong, not the users.

### 10. Ideas deliberately not recommended

- **Async/streaming rewrite of the web layer** — sync handlers in a threadpool are fine at localhost scale; the complexity isn't earned.
- **Vector/embedding recipe matching** — word-boundary substring scoring is transparent, debuggable, and correct at this scale; revisit only if aliases stop being maintainable.
- **Fighting the no-defaults schema invariant** to save prompt tokens — the invariant is load-bearing; the token cost is trivial.
- **Direct USB** — the backlog's "skip indefinitely" verdict is right; nothing here changes it.
