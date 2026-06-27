# Working on this project

This is a "how we work" doc — not a contributor guide for outside contributors. The project is licensed [PolyForm Noncommercial](LICENSE); outside contributions aren't actively solicited.

The intended audience is the author and any Claude Code (or similar) agent paired in on the work. The full design rationale is in [`docs/superpowers/specs/2026-06-27-issue-workflow-design.md`](docs/superpowers/specs/2026-06-27-issue-workflow-design.md); this file is the operational version.

## Kickoff

The user says **"let's do #N"** (or Claude suggests an issue and the user confirms). One issue at a time. Nothing runs automatically.

## Two paths

| Path | Triggers when | Mechanism |
|---|---|---|
| **Trivial** | One file, ≤ ~30 min, data/doc/README/single-recipe | Edit on main checkout → commit → push. No branch, no PR, no agent reviews. |
| **Real** | Multi-file, > ~30 min, code change | Worktree + branch + PR + three agent reviews + human review |

If you can't decide which, treat it as Real. The cost of an unnecessary PR is small; the cost of skipping review on something that needed it is larger.

## Real-issue flow

### 1. Pick

```bash
gh issue view <N>     # re-read the scope cold
```

If the scope has held up, proceed. If anything's changed, update the issue first.

### 2. Set up the worktree

```bash
cd ~/Development/me80-tone-gen
git worktree add ../me80-tone-gen-worktrees/feat-NN-short-name -b feat/NN-short-name
cd ../me80-tone-gen-worktrees/feat-NN-short-name
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'

# The security-review skill resolves `origin/HEAD` for its diff; new worktrees
# don't always have it set, and the skill errors if it's missing.
git remote set-head origin main
```

Branch naming: `feat/NN-short-name`, `fix/NN-short-name`, `chore/NN-short-name`, `docs/NN-short-name`. `NN` is the issue number.

### 3. Implement

- Tests are written alongside new behavior. No TDD ceremony; no test-after laziness.
- Mid-work decisions stay in chat. Don't manufacture a paper trail.
- Check in with the user when an ambiguous call has non-trivial cost, when the issue's scope no longer makes sense, or when a surprise comes up. Otherwise work continuously.
- If the work is bigger than the issue suggested, stop and renegotiate scope rather than silently expanding.

### 4. Open the PR

```bash
git push -u origin feat/NN-short-name
gh pr create --title "<short imperative>" --body "Closes #NN.

<one-to-three line why>

<acceptance per the issue>"
```

### 5. Three agent review passes (in order)

```
1. Agent code review     ← Skill: superpowers:requesting-code-review
   Correctness, architecture, missed edge cases.
   Address real findings, push fixups.

2. Agent simplify pass   ← Skill: simplify  
   Over-engineering, dead code, single-caller helpers, unnecessary abstractions.
   Findings are ADVISORY. Reject anything that hurts clarity or removes a
   deliberate seam. Not optimizing for line count.

3. Agent security review ← Skill: security-review
   Secrets, injection, path traversal, CORS, leaked auth, deserialization.
   Especially important post-#9/#10 with external API integrations.
```

If simplify made > 5-line changes that affect logic, re-run code review briefly before security. Otherwise proceed straight through.

### 6. Human review

You read the diff in PR view (`gh pr view --web`), cold. Different mental mode than editor — catches different things. The agents are scaffolding; your eyes are the final gate.

### 7. Merge & clean

```bash
gh pr merge --squash --delete-branch
cd ~/Development/me80-tone-gen
git pull
git worktree remove ../me80-tone-gen-worktrees/feat-NN-short-name
```

Squash for clean linear history on main; the branch's intermediate commits stay in the PR for posterity. "Closes #NN" in PR body auto-closes the issue.

### 8. Verify (when relevant, can happen after merge)

| Change touches | Verification |
|---|---|
| Recipe values | Ear-test priority recipes through the pedal; mark untested honestly with `confidence: "untested"`. Don't gate merge on slow physical-world feedback. |
| Writer / `.tsl` format | Generate a `.tsl`, import into BTS, confirm it loads. ~2-min smoke. |
| Web UI | Server smoke (agent does), browser eyeball (human does). |
| Pure refactor | Tests pass = good. |

## Trivial-issue flow

```bash
# Edit directly in main checkout
vim <file>

# Commit + push
git add <file>
git commit -m "..."
git push
```

Trivial means: README polish, single recipe add, docstring fix, typo. If the change touches Python code, lean toward Real.

## Commit messages

- Imperative title under 70 chars
- Body explains *why* if non-obvious
- `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer when paired
- Reference issues: `Closes #N`, `Refs #N`, `Part of #N`

## Releases

Occasional, every 3–5 issues. No fixed cadence.

```bash
# Bump version in pyproject.toml
git tag -a vX.Y.Z -m "<short summary>"
git push --follow-tags
gh release create vX.Y.Z --title "..." --notes "..."
```

Patch / minor / major per [SemVer](https://semver.org). v0.x.y while pre-1.0.

## Where work lives

| Work type | Where |
|---|---|
| Concrete actionable items | GitHub Issues |
| Pre-issue ideas, investigation needed | [`BACKLOG.md`](BACKLOG.md) |
| Half-formed ideas, longer narrative, "what if X" notes | Author's Obsidian "Tone Program" vault |
| Project plan + status | Obsidian's `00 — Project Plan & Status.md` |
| Workflow design rationale | [`docs/superpowers/specs/`](docs/superpowers/specs/) |

## Test discipline

- `pytest` must pass on `main` at all times. If it doesn't, fixing it is more urgent than queued work.
- Without `data/Contra_1.tsl`, 25/34 tests pass and 9 skip — run `./scripts/fetch_reference.sh` for the full suite locally.
- Generator unit tests use a `FakeOllama` client. Never hit real Ollama in unit tests, only in manual smoke tests.

## Working with Claude

- Pair-programming style: Claude opens the branch, makes changes, opens the PR. Author reviews the diff and merges (or asks for changes).
- One issue per session keeps context tight.
- Claude reads `CLAUDE.md` at session start — invariants and pointers live there. This file is the operational counterpart.
