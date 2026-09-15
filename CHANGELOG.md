# Changelog

Versions track `plugins/model-routing/.claude-plugin/plugin.json`. Bump it with every
change to the plugin directory, or installed copies never update.

## 2.1.1 — 2026-09-14

Corrections from a second machine's audit.

- **`check-delegation.py` counts each API message once.** The logs repeat a message's
  usage once per content block, 2–4× depending on the model, so every share it
  printed was skewed. Same fix applied to the new `model-usage-audit.py`, which also
  prices by model, splits main thread from subagents, and classifies what each
  top-tier request did.
- **`ROUTING.md` no longer claims delegating keeps the main context small.** Two
  machines, ~2,300 handoffs, no such effect. The reason to delegate is the worker's
  price.
- README re-sources the August→September subagent swing to the machine and method it
  came from (73% Sonnet → 84% top-tier, deduped, list prices) and notes the second
  machine did not show it.

## 2.1.0 — 2026-09-14

Three assistants for where the money actually went.

- **`tester` (Sonnet).** Writes tests for behaviour that already exists and never
  touches the code under test. One scenario per test, fixtures copied exactly, the
  runner's own pass/fail count reported. Test-writing lanes were 56% of top-tier
  subagent spend in the September audit.
- **`reviewer` (Sonnet).** Reads a diff and reports defects with file and line; never
  fixes. Distinct from `checker`, which asks whether the work is finished. Review
  passes were the most-spawned subagent in the audit, all generic.
- **`shipper` (Sonnet).** Rebase, push, open or update the PR, read the failing CI
  command, answer review threads. Never merges, never force-pushes a shared branch.
- `ROUTING.md` lists the new assistants, cheapest first.

## 2.0.0 — 2026-09-14

One plugin instead of two.

- **`model-routing-note` is retired.** Its session-start note now ships inside
  `model-routing`. Uninstall the old one; it no longer exists in the marketplace.
- **The note is a file, `ROUTING.md`.** Same text at the repo root and inside the
  plugin, so it can be pasted into `AGENTS.md` for Codex, Cursor, or any tool with no
  hook layer.
- **Per-project override.** If the repo has `.claude/routing.md`, the hook injects
  that instead of the default note.
- **New `editor` assistant on Haiku** for mechanical edits with zero design decisions:
  renames, version bumps, moving files, applying a given diff, lint and format fixes.
- **The note now tells the session to name a model on every worker it spawns**,
  cheapest first, in addition to delegating by default.
- **Session-start hook rewritten in Python** (reads the note from disk, fails silent)
  rather than a bash `printf` of inline JSON.
- README rewritten for the single plugin, with the 2026-09-14 audit numbers, guidance
  for other tools, and a prior-art section.

Why: on one machine, the month the main session moved to Fable, subagent spend went
from 87% Sonnet to 57% Fable because unnamed spawns inherit the parent model. The note
plugin, being separate and "pilot first", had never been turned on.

## 1.1.1

- `model-routing`: PreToolUse hook gives any generic subagent spawned without a model
  a Sonnet default. Never overrides an explicit model or a named agent's own model.

## 1.1.0

- `model-routing-note`: SessionStart hook attaching the delegate-by-default note.

## 1.0.0

- Five assistants pinned to cheap models: `finder` (Haiku), `researcher`, `builder`,
  `analyst`, `checker` (Sonnet).
