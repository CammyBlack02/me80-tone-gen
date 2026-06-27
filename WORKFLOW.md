# Working on this project

This is a "how we work" doc — not a contributor guide for outside contributors. The project is licensed [PolyForm Noncommercial](LICENSE); outside contributions aren't actively solicited.

The intended audience is the author and any Claude Code (or similar) agent paired in on the work. The goal: enough structure to stay disciplined, not so much that it becomes ceremony.

## Decision: where work lives

| Work type | Where |
|---|---|
| Typos, comment edits, one-line fixes, README polish | Direct commit to `main` |
| A new recipe in `recipes.json` | Direct commit to `main` |
| Anything multi-file or > a few minutes | Issue + feature branch + PR |
| Half-formed ideas, "what if X" notes, longer narrative | Obsidian (`Personal Mac/Tone Program/`) — not committed |
| Broad project plan + status | Obsidian's `00 — Project Plan & Status.md` |
| Decision log: "why we picked X over Y" | Obsidian; promote to a repo doc only if it shapes contributor behaviour |

## Branch + PR convention (for the multi-file work)

```bash
# Start from a fresh main
git checkout main && git pull

# Branch named feat/<thing>, fix/<thing>, chore/<thing>, or docs/<thing>
git checkout -b feat/visual-pedalboard

# ... do the work ...

# Push the branch
git push -u origin feat/visual-pedalboard

# Open a PR (reads "closes #N" or "refs #N" to link the issue)
gh pr create --title "Visual pedalboard UI" --body "Closes #1. ..."

# Self-review: read the diff in the PR view cold, not in your editor
gh pr view --web

# Merge when satisfied — squash is fine for tidy history
gh pr merge --squash --delete-branch
```

The point of the PR even when solo: reading the diff in PR view is genuinely different from reading it in your editor. You catch things.

## Commit messages

Title under 70 chars, imperative ("Add X" not "Added X"). Body explains *why* if non-obvious. Reference issues with `closes #N`, `refs #N`, `part of #N`. Co-author trailer for Claude-paired work.

Example:

```
Add visual pedalboard component to web UI

Replaces the text-only knob list with an SVG signal-chain view.
Each block renders as a card; rotary knobs draw as dial positions
mapped from 0-99 to 270° rotation.

Closes #1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Issue hygiene

- One concrete actionable thing per issue. "Recipe expansion" is fine if scoped to the gaps listed; "make the tool better" is not.
- Use labels: `recipes`, `ui`, `infrastructure`, `prompt-engineering`, `enhancement`, `bug`, `documentation`. Keep the set small.
- Close issues via commit message (`closes #N`) — keeps the link in history.
- Don't create issues for ideas you might never do. That's what Obsidian is for.

## Releases

- Patch / minor / major per [SemVer](https://semver.org). v0.x.y while we're pre-1.0.
- Release process:
  1. Make sure `main` is clean, tests pass, version bumped in `pyproject.toml`.
  2. `git tag -a vX.Y.Z -m "<short summary>"` and `git push --follow-tags`.
  3. `gh release create vX.Y.Z --title "..." --notes "..."` — paste notes from the changelog of work since the previous tag.

## Test discipline

- `pytest` should pass on `main` at all times. If it doesn't, fixing it is more urgent than whatever else is queued.
- Tests anchored to the optional `data/Contra_1.tsl` reference will skip when it's absent — run `./scripts/fetch_reference.sh` locally if you want the full suite.
- New code paths get tests where the test would catch a real bug, not as a ritual.

## Working with Claude

- Pair-programming style: Claude opens the branch, makes the changes, opens the PR. Author reviews the diff and merges (or asks for changes).
- Prefer one issue per session — keeps context tight and the diff bounded.
- Claude reads `WORKFLOW.md` and `CLAUDE.md` at session start. Anything important to remember between sessions goes in those docs or in Claude's memory system, not buried in a chat scrollback.
