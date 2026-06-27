# Issue workflow — design

Date: 2026-06-27
Status: approved, pending implementation in WORKFLOW.md + CLAUDE.md
Brainstormed with: Cameron + Claude Opus 4.7 (1M context)

## Purpose

Define the end-to-end workflow for tackling GitHub issues on `me80-tone-gen` after v0.1.0. The v0.1.0 build was direct-to-main rapid prototyping; post-release work is structured around 11 open issues (one umbrella, 10 specific) and needs a consistent flow that's lightweight enough to feel natural and rigorous enough to avoid the obvious failure modes.

## Constraints

- **Solo project**, one human (Cameron) + one AI agent (Claude Code).
- **PolyForm Noncommercial** licensed; no outside contributors expected.
- **Lightweight bias.** v0.1.0 shipped in a session; the workflow shouldn't introduce friction that wouldn't have shipped v0.1.0.
- **Some issues are project-specific** in ways that need hardware testing (recipe value tuning, format verification).

## Decisions

These were chosen during the brainstorm, recorded here so future-Cameron knows the *why*:

| Decision | Choice | Why |
|---|---|---|
| Default rigor | Lightweight | Matches v0.1.0 cadence; heavier ceremony wasn't needed to ship correctly. |
| Mid-work decision log | Inline in chat, no record | Code is the artifact. Substantive design notes go to Obsidian only when worth re-finding. |
| Test discipline | Tests alongside code | TDD ceremony was unnecessary for v0.1.0 (34 tests at MVP). Same approach scales. |
| Worktrees | For big issues only | Isolation matters when several things are in flight or you want `main` always demo-ready. Small issues don't need them. |
| Code review agent | Yes, on every PR | We're AI-paired; explicit review pass catches AI's habits. |
| Simplify agent | Yes, on every PR | AI over-elaborates. Counter-pressure. Suggestions are advisory, not mandatory. |
| Security review agent | Yes, on every PR | FastAPI server present + external API integrations coming (#9, #10). Hygiene now, not later. |
| Human review | Always last, in PR view | Agents are scaffolding; human eyes are the final gate. |
| Release cadence | Occasional, every 3–5 issues | No fixed schedule. Tags are cheap; release when work feels coherent. |

## The flow

### Kickoff

> User: "Let's do #N."

Or Claude suggests an issue and the user confirms. That's the trigger — nothing happens automatically; nothing is queued behind it. One issue at a time.

### Phase 1: Pick

1. Re-read the issue cold. Has the scope held up? Has anything changed since it was written?
2. Decide path:
   - **Trivial** (one file, ≤ ~30 min, data/doc/README/single-recipe) → direct-to-`main` checkout, no branch, no PR
   - **Real** (multi-file, > ~30 min, code change) → worktree + branch + PR
3. If unclear after re-reading, ask. If genuinely ambiguous, invoke `EnterPlanMode`. Otherwise skip planning ceremony.

### Phase 2: Implement

**Real-issue setup:**

```bash
cd ~/Development/me80-tone-gen
git worktree add ../me80-tone-gen-worktrees/feat-NN-short-name -b feat/NN-short-name
cd ../me80-tone-gen-worktrees/feat-NN-short-name
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

**Implementation rules:**

- Tests are written alongside new behavior (not before, not after).
- Claude works continuously; checks in with the user when:
  - A decision could go multiple ways and the cost of being wrong is non-trivial
  - The issue's scope no longer makes sense as written
  - A surprise comes up the issue didn't anticipate
- Mid-work decisions stay in chat. Don't manufacture a paper trail.
- If you discover the work is bigger than the issue suggested, stop and renegotiate scope rather than silently expanding.

**Trivial-issue setup:** skip the worktree dance. Edit directly in the main checkout, commit to `main`, push.

### Phase 3: Review (PR-shaped issues only)

```bash
git push -u origin feat/NN-short-name
gh pr create --title "..." --body "Closes #NN. ..."
```

Then the review sequence, in order:

1. **Agent code review** — invoke `superpowers:requesting-code-review`. Checks correctness, architecture, edge cases. Findings go to chat / PR comments. Address real findings, push fixups.

2. **Agent simplify pass** — invoke `simplify` skill. Looks for over-engineering, dead code, unnecessary abstractions, single-caller helpers. Findings are *advisory* — reject anything that hurts clarity or removes a deliberate seam. We're not optimizing for line count.

3. **Agent security review** — invoke `security-review` skill. Particularly relevant given the FastAPI server and upcoming external integrations (Spotify, MusicBrainz, Equipboard). Address real findings.

4. **Lazy re-validation:** if simplify made > 5-line changes that affect logic, re-run code review briefly. Otherwise proceed.

5. **Human review** — user reads the diff in the PR view (not in editor — different mental mode, catches different things). Approve, request changes, or kick back.

6. **Merge** when all four passes are satisfied.

```bash
gh pr merge --squash --delete-branch
```

Squash gives `main` a clean linear history; the branch's intermediate commits live in the PR for posterity.

### Phase 4: Cleanup

```bash
cd ~/Development/me80-tone-gen
git pull
git worktree remove ../me80-tone-gen-worktrees/feat-NN-short-name
```

Issue auto-closes via "Closes #NN" in the PR description.

### Phase 5: Verify (when relevant)

Some issues' acceptance includes verification beyond test-pass:

- **Recipe-affecting issues** (#7 and any future recipe work): priority recipes get ear-tested through the actual pedal. Recipes not yet tested ship with `confidence: "untested"` — that's honest, not a blocker. Test more as you play.
- **Writer / format-affecting issues**: regenerate a `.tsl` after merge, import into BTS, confirm it loads. ~2 minute smoke test.
- **Web UI changes**: server smoke test (the agent does), browser eyeball (the human does). Only block if something is actually broken.
- **Pure refactor / non-functional**: tests pass = good enough.

Verification can happen *after* merge for non-blocking checks (recipe ear-testing especially). Don't gate the merge on slow physical-world feedback.

### Phase 6: Release (occasional)

When 3–5 issues have landed and the work feels coherent:

```bash
# Bump version in pyproject.toml (and README badge if we add one)
git tag -a vX.Y.Z -m "<short summary>"
git push --follow-tags
gh release create vX.Y.Z --title "..." --notes "..."
```

No fixed cadence. Tags and releases are cheap; lean toward more rather than fewer.

## When to skip review passes

- **Trivial issues** (direct-to-main, no PR): no agent reviews. Self-review carefully before pushing.
- **Real issues** (PR): all three agent reviews always. No "this is small enough to skip" inside the PR path. If it's big enough to PR, it's big enough to review.
- **Data-only PRs** (e.g. only `recipes.json` changed): security review is overkill but quick — run it anyway. Cost of running is low; cost of skipping and missing something is higher.

## Comparison to v0.1.0 workflow

What we added:
- Branch + PR for real issues (we direct-committed during MVP)
- Worktrees for big issues
- Three agent review passes per PR (code / simplify / security)
- Human PR-view review (different mental mode)

What we kept:
- Tests alongside code
- Commits driven from chat
- No design docs per issue
- No mid-work decision log
- Direct-to-main for trivial work

What we did NOT add:
- TDD discipline
- Plan-mode-by-default
- Per-issue design docs
- Project boards / milestones
- Mandatory ear-testing as merge gate

## Overhead estimate

- Trivial issue: ~minutes, unchanged from v0.1.0 pace.
- Real issue: implementation + 8–20 min agent reviews + your PR-view read. For the 10 queued specific issues, ~1.5–3 hours of review time total across the lot.

Acceptable cost for catching real bugs early and maintaining audit-traceable history.

## Open follow-ups (not blockers)

- The agent review passes work on PR branches; we'll need to verify the agents play well with this codebase the first time we use them. First real-issue PR is the de-facto pilot.
- If the simplify pass produces consistently bad suggestions, we revisit whether it's worth keeping. Likely fine but worth watching.
- If review pass overhead feels heavy after 2–3 PRs, we'll trim.

## Next steps

1. Update `WORKFLOW.md` to reflect this flow (replaces the v0.1.0-era sketch).
2. Update `CLAUDE.md` where invariants emerged (e.g. "agents run in this order").
3. Pick the first issue. (Currently leaning #1 visual pedalboard UI.)
