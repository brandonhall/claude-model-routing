# Changelog

Versions track `plugins/model-routing/.claude-plugin/plugin.json`. Bump it with every
change to the plugin directory, or installed copies never update.

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
