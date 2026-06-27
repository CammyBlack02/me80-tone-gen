# Claude context for this project

This file gets loaded at the start of every Claude Code session. Keep it tight — facts, invariants, and pointers. Process lives in [WORKFLOW.md](WORKFLOW.md); narrative lives in the author's Obsidian vault.

## One-line summary

Local-only natural-language → Boss ME-80 patch (`.tsl`) generator. CLI + FastAPI web UI, both thin shells over a shared core. LLM inference via Ollama on the author's machine. PolyForm Noncommercial licensed.

## Pointers

- **`README.md`** — user-facing overview, install, usage
- **`WORKFLOW.md`** — how the author + Claude work on this (branches, PRs, releases, test discipline)
- **`BACKLOG.md`** — pre-issue ideas, investigation-needed work
- **GitHub issues** — concrete actionable work, especially the tone-accuracy umbrella (`#6`)
- **The spec** (author's iCloud, not in repo) — original design doc. Single source of truth for the `.tsl` format. If you don't have access to it, the headers/numbering Claude refers to (`§3.4`, `§4`, `§9.1`, etc.) are in there.
- **Author's Obsidian "Tone Program" vault** (not in repo) — longer-form decision log + project plan doc. Updates land there for substantive design notes.

## Architectural invariants (don't violate without discussion)

- **Core module pattern.** Business logic lives in `writer.py`, `renderer.py`, `generator.py`, `recipes.py`. The CLI (`cli.py`), the FastAPI app (`web.py`), and any future interfaces are thin shells that call core functions. No LLM calls, no patch construction, no validation inside route handlers or argparse blocks.
- **No Pydantic field defaults on `SemanticPatch` or its blocks.** Every field is required. Defaults caused the model to skip fields and lie in the rationale ("includes spring reverb" while reverb block was off). Re-introducing defaults is a regression. If you think you need one, you don't — set the value explicitly at every call site.
- **Same core powers all interfaces.** The CLI and web UI never duplicate logic. If you add a feature to one, the other gets it via the core.
- **No business logic in FastAPI route handlers.** Routes marshal request/response shapes; they don't generate, validate, or write `.tsl` files. Anything more than that goes into the core.

## Hardware-verified facts (don't second-guess)

- **Knob max is 99, not 100.** Verified by a deliberate max-knob export from the actual pedal on 2026-06-27. `_clamp_knob` clamps to `min(99, …)`; Pydantic `Knob` is `le=99`; LLM prompt says "0-99". BTS will accept 100 if we send it, but the hardware writes 99 at physical max — we match hardware.
- **BTS imports writer-built `.tsl` files cleanly.** Confirmed on hardware. No "hidden required fields" missing from the 82-key params dict.
- **The 82-key params shape is exhaustive.** Verified against `Contra_1.tsl` (real BTS export). Any field added or removed needs the same conformance check.
- **`name1..16`, `patchname`, and patch-level `name` must agree.** All three encode the same 16-char space-padded string. The writer's `encode_name` computes them together; never set them independently.
- **`liveSetId` is identical across every patch and the top-level `liveSetData.id`.** Spec §3.2 invariant; the writer enforces it, tests check it.
- **`amp_sw` is always `"1"`.** Preamp is always on by hardware design.

## Style & conventions

- **Comments only when the *why* is non-obvious.** Never explain *what* the code does — well-named identifiers do that. Don't reference the current task, fix, or callers ("added for the Y flow", "fixes issue #X") in comments; those belong in commit messages.
- **No emojis in code or docs** unless the author explicitly asks. README and WORKFLOW are deliberately emoji-free.
- **Imperative commit titles** under 70 chars. Body explains *why* if non-obvious. `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer on paired work.
- **Sentences not abbreviations** in user-facing strings (CLI output, web UI labels, error messages).
- **Tests live in `tests/`, organized by module** (`test_writer.py`, `test_generator.py`, `test_recipes.py`). Use fixtures for shared setup. Mock the Ollama client rather than calling it in unit tests.

## Test discipline

- `pytest` must pass on `main` at all times. Fixing failures is more urgent than queued work.
- Without `data/Contra_1.tsl` (the upstream sample, not bundled — see WORKFLOW.md), 25/34 tests pass and 9 skip cleanly. Run `./scripts/fetch_reference.sh` to get the full suite locally.
- Generator unit tests use a `FakeOllama` client (see `tests/test_generator.py`) — never hit the real Ollama in unit tests, only in manual smoke tests.

## Anti-patterns (things we've already gotten wrong; don't redo)

- **Don't re-introduce Pydantic field defaults** on `SemanticPatch` blocks. The model gets lazy and lies in `rationale`. See `src/me80_tone_gen/schema.py` — every field is required for a reason.
- **Don't widen `_clamp_knob` to allow values > 99.** Hardware caps at 99.
- **Don't put `Contra_1.tsl` back in the repo.** Upstream has no license. Use `scripts/fetch_reference.sh` for local dev.
- **Don't curate recipe values without ear-testing through the pedal** if you can ear-test. Mark untested recipes with `confidence: "untested"` (once `#7` lands the field). The "I asked Claude what the gain should be" path is fine as a seed but not as a verified value.
- **Don't broaden recipe aliases unilaterally.** Specific aliases keep recipes from triggering on irrelevant descriptions. Broader aliases ("metal rhythm" → MoP) are useful when a genre has only one recipe, but verify the routing makes sense before adding.
- **Don't run destructive git operations** — force-push to main, history rewrites, tag deletions — without explicit author approval, even when the autonomous-mode flag is set.

## When something feels ambiguous

- **Defer to the spec headers** (`§3.4`, `§4`, etc.) — those are the canonical decisions. If the spec and the code disagree, the code probably needs to change.
- **Defer to hardware** — facts verified against the actual pedal trump any model intuition.
- **Defer to existing patterns** in the codebase — if there's already a similar function, match its style. Consistency over cleverness.
- **Ask the author** if a decision could go multiple ways and the cost of being wrong is high (commits to main of significant changes, API contracts, license-affecting changes, anything destructive).
