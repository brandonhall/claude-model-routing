# Model routing

Use the right model for the job. The session runs on Sonnet by default and does the
ordinary work itself; the expensive model is on call for the decisions that need it,
through an `architect` assistant that gets a compact brief instead of the whole
conversation; and the grinding that is worth parallelising goes to cheap pinned
assistants. One plugin, applied to everyone automatically, with nothing to remember.

No model is blocked. Anyone can open an Opus or Fable session for a design conversation
at any time, and that is the right tool for that. The goal is not to take power away;
it is to stop paying top-tier prices for a tool loop. Two machines' logs on 2026-09-14
showed 76–86% of top-tier main-session spend going to requests that ran a shell
command, fetched data, or edited a file, and under 4% to thinking tokens.

## What it does

Four things, all in the one `model-routing` plugin.

### 1. Ten shared assistants, each pinned to the cheapest model that does its job

| Assistant    | Runs on | Handles                                                        |
| ------------ | ------- | -------------------------------------------------------------- |
| `finder`     | Haiku   | Locating files and strings in the filesystem                   |
| `editor`     | Haiku   | Mechanical edits with zero design decisions — renames, bumps, moving files, applying a given diff, lint fixes |
| `researcher` | Sonnet  | Reading external documentation and reporting back              |
| `analyst`    | Sonnet  | Spreadsheets, data pulls, reducing long output                 |
| `tester`     | Sonnet  | Tests for behaviour that already exists; never touches the code under test |
| `reviewer`   | Sonnet  | Finds what is wrong in a diff or PR; reports, never fixes      |
| `shipper`    | Sonnet  | Rebase, push, open the PR, read failing checks, answer review threads; never merges |
| `builder`    | Sonnet  | Completing a scoped piece of work end to end (the default)     |
| `checker`    | Sonnet  | Independently verifying finished work                          |
| `architect`  | Fable   | On call for one expensive decision at a time — cross-system approach, a bug that survived two fixes, auth / isolation / payments / production data, a long-lived tradeoff. Gets a brief, returns a decision and a step plan. Never implements. |

The model is fixed in each assistant's file, so this work lands on a fast, low-cost
model whether or not the person thinks about it. The expensive model stays on the
planning, integration, and final call, which is what it's for.

Assistants finish their own piece and never stall waiting on a decision — they proceed
on a stated assumption and flag it. The session owns finishing the whole project, and
uses `checker` to confirm it rather than trusting its own summary.

### 2. A default model for every other subagent

Other tools spawn their own subagents — the Superpowers plugin does it in half a
dozen skills, for code review, plan execution, and parallel work. None of them name
a model, so those workers inherit whatever the main session is running. Delegating from
a Fable session gets you a Fable worker: you save context but not cost.

Measured on one work laptop on 2026-09-14 with `model-usage-audit.py` (one count per
API message, list prices): in August, 73% of subagent spend was Sonnet; in September,
after the main session moved to Fable 5.1, 84% of subagent spend was on Fable or Opus
(61% Fable 5.1), with no change in the kind of work. A second machine whose subagents
were already mostly Sonnet showed no such swing. Run the script on your own machine
before assuming either number.

A hook fills that gap. When a subagent is spawned **without** an explicit model, it gets
Sonnet. When one **is** named — on the call, or in an agent's own file — the hook leaves
it completely alone. It supplies a default, it never overrides a choice.

Sonnet rather than Haiku because these generic spawns do real work (a code review, a
plan step), and Haiku's smaller context window is a poor fit for reading a large diff.
Haiku stays where it belongs, on `finder` and `editor`.

The built-in `Explore` agent is the one worth knowing about: on claude.ai accounts it
inherits the session's model capped at Opus, so from a Fable or Opus session it ran on
Opus before this hook existed, and `CLAUDE_CODE_SUBAGENT_MODEL` never touched it. The
hook's Sonnet default is a real step down there, not a no-op.

### Every hand-off is named

On every spawn the hook hands the session one line — the assistant, the model, and how
that model was chosen (named on the call, pinned by the assistant's file, or defaulted
by the hook) — and the note tells it to state that line in its reply with the reason:
`→ Tester (sonnet, pinned): write regression tests`. The desktop's own tool row shows
the assistant name as well. This is deliberately not a pop-up notice: those render
collapsed in the desktop app and hide the tool row behind a click.

The line travels as `additionalContext` on the `PreToolUse` hook, which Claude Code
honours from 2.1.221 (verified in that binary's hook schema and runner). On an older
binary the line is dropped silently and nothing else changes: the Sonnet default still
applies, so the failure mode is a missing sentence, not a wrong model.

### 3. A standing note on when to reach up and when to hand down

[`ROUTING.md`](ROUTING.md) is attached to the start of every session. To a Sonnet
session it says: do the ordinary work here, reach up to `architect` only for the four
kinds of decision listed above, and give it a brief rather than the conversation. To an
Opus or Fable session it says: you are the architect, so decide here and hand the tool
loop down. Either way it tells the session to name a model on every worker it spawns,
cheapest first.

A project can override the note: put your own text at `.claude/routing.md` in the repo
and the hook injects that instead of the default.

### Why farming out wins even on small tasks

A handoff isn't free — it costs a fresh context plus a report to read back, roughly
1.5× the raw tokens. But the model prices are 5–10× apart (Fable 5.1 $10/$50 per
million tokens in/out, Sonnet 5 $2/$10, Haiku 4.5 $1/$5 — list prices as of
2026-09), so the trade is lopsided:

| Path                              | Relative cost |
| --------------------------------- | ------------- |
| Fable does it directly            | 1.0×          |
| Sonnet does it, including handoff | ~0.3×         |
| Haiku does it, including handoff  | ~0.15×        |

One claim an earlier version of this README made is **not** borne out by the logs:
that delegating keeps the main session's context small. On two machines and roughly
2,300 handoffs, sessions that delegated more did not have smaller main contexts
(correlation +0.04 on one, +0.32 on the other). The report comes back into the main
context, and the main session still reads the diff. The saving is the price of the
worker's model, not a smaller main thread.

## Other tools (Codex, Cursor, anything that reads AGENTS.md)

Those tools have no hook layer, so the plugin can't pin models for them. What they do
have is an instruction file. Paste the contents of [`ROUTING.md`](ROUTING.md) into the
repo's `AGENTS.md` (or the tool's rules file) and the same "plan here, delegate the
rest, cheapest model first" behaviour applies. Pin the assistants' models in that
tool's own agent configuration; Codex, for one, has no global default for subagent
models, so each agent definition needs its own.

## What is enforced and what is only words

| Piece | Enforced? |
|---|---|
| An assistant's pinned `model:` | Yes, by the harness. The one override is a caller naming a model on the call itself; the plugin never does that. |
| Sonnet default for unnamed spawns | Yes, the hook rewrites the call before it runs. To rewrite it the hook must also answer `allow`, so a generic spawn skips any permission prompt it would otherwise get (`updatedInput` does not work with `ask`). Blind spot: coordinator mode drops the model field. |
| The routing note | No. It is text the session reads. It shapes behaviour; it does not bind it. |
| `model` in managed settings | A default, not a lock. `/model` still works. |
| `maxEffortLevel` in managed settings | A cap (`low` / `medium` / `high` / `xhigh`). From 2.1.267 the lowest cap from any scope wins; before that, managed settings win as usual. |
| `availableModels` in managed settings | A real allowlist users cannot widen. It also governs subagent frontmatter and the Agent tool's `model` parameter, and an excluded subagent runs on a fallback model with no error, so the list must include `fable` or `architect` silently becomes a Sonnet agent. Not recommended to start — see below. |

## Deploy

1. This repo is public on GitHub; a private fork works the same way.
2. In Claude admin settings, go to **Organization settings → Plugins** and add the
   repo as a plugin marketplace.
3. Mark **`model-routing`** as **Installed by default**. It then appears in every
   member's installed list with no action on their part; members can still
   uninstall it.

For anyone using the Claude Code CLI rather than the desktop app, add this to managed
settings as well. **Both keys are needed** — the first registers the source, the second
actually turns the plugin on. With only the first, people get a prompt they can skip.

```json
{
  "extraKnownMarketplaces": {
    "claude-model-routing": {
      "source": { "source": "github", "repo": "YOUR-ORG/claude-model-routing" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "model-routing@claude-model-routing": true
  },
  "model": "sonnet",
  "maxEffortLevel": "high",
  "autoCompactWindow": 200000,
  "bashOutputMaxChars": 15000,
  "env": {
    "MAX_MCP_OUTPUT_TOKENS": "10000"
  }
}
```

The extra keys are the org defaults this plugin assumes. `model` is a default,
not a lock: anyone can `/model fable` for a design session, and the managed value
reapplies on the next launch. `maxEffortLevel` is a cap: on both audited machines,
`max` produced *fewer* thinking tokens per request than `high`, so it was buying
nothing.

`autoCompactWindow` and the two output caps attack the other half of the bill. Every
step re-sends the whole session history; on the audited machine, requests past the
hundredth in a session were 72% of top-tier main-session spend, re-reading 470–660K
tokens to take one small step. A 200K compaction ceiling means no step re-reads more
than that. The output caps keep long logs from piling into the history in the first
place; the assistant still sees the tail, where failures are. Cache TTL is deliberately
left at its default: modelled against real request gaps, the 5-minute TTL would have
cost 14–26% more than the 1-hour one.

Do **not** add `CLAUDE_CODE_SUBAGENT_MODEL` to the `env` block. Before Claude Code
2.1.251 that variable outranked both the Agent tool's `model` parameter and an agent's
own `model:` frontmatter, so on any older binary it would force `architect` onto Sonnet
and override every explicit model a caller passes. The hook already does the job it
was for, and unlike the variable it covers `Explore` and `Plan`.

Do not add an `availableModels` allowlist at first. Run a month, then run
`model-usage-audit.py`; if Fable sessions are creeping back as tool loops, add it then,
and keep `fable` in the list: the allowlist applies to subagent models too, and an
excluded `architect` degrades to a fallback model without an error.

### When to open a Fable or Opus session anyway

Brainstorming a feature for an hour. Working through a design with a person. Reading a
long document and arguing with it. Anything where the deliverable is the conversation
itself. That is the 14–24% the expensive model is actually for, and a subagent with a
brief is the wrong shape for it. The note recognises when it is running on Opus or
Fable and tells that session to decide there and hand the execution down.

### Updates are not automatic unless you say so

Claude Code auto-updates plugins from Anthropic's own marketplaces, but a third-party
marketplace like this one has auto-update **off** by default. `"autoUpdate": true` on the
entry above turns it on; Claude Code then checks once per session, in the background,
and applies the new version on the next launch. Anyone who registered the marketplace
by hand can flip the same switch in `/plugin` → Marketplaces → this marketplace →
Enable auto-update, or update once with:

```bash
claude plugin marketplace update claude-model-routing
claude plugin update model-routing@claude-model-routing
```

`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` looks like belt and braces for the hook. It is
not, before Claude Code 2.1.251: there it overrides pinned and per-call models too, so
it would demote `architect`. Leave it unset and let the hook do this job; it also
covers `Explore` and `Plan`, which the variable never did.

### What to watch after rollout

Delegation costs a round trip. Measured on one machine over the 60 days to
2026-09-14, across 2,300 handoffs, the median was about 10 minutes, with the middle
half between 5 and 22 minutes — most of that is the assistant doing real work, not
overhead, but it is time the person waits. That's a good trade on a half-hour task
and a bad one on a quick question. After a week, ask people
one thing: **did anything get slower?** If the people doing short, conversational work
say yes while the people doing long build work say no, loosen the "delegate when"
floor in `ROUTING.md` before anything else.

## Learning about it from a session

Just ask. The assistant list, with each one's description, and the routing note are in
every session's context, so "what assistants do I have?" or "which model would this
land on?" gets answered with no command. There is deliberately no slash command for
this. For the component inventory, `/plugin` in a session or
`claude plugin details model-routing@claude-model-routing` in a shell.

## Changing it

Each assistant is one short file in `plugins/model-routing/agents/`. Two lines matter:

- `model:` which engine it runs on
- `description:` when Claude should hand work to it

The session note is `ROUTING.md` at the repo root; `plugins/model-routing/ROUTING.md`
is the copy the hook ships, so keep them identical (`cp ROUTING.md plugins/model-routing/`).

Edit, commit, push — **and bump `version` in
`plugins/model-routing/.claude-plugin/plugin.json`**. If the version string doesn't
change, updates are skipped and your edit never reaches anyone.

## Checking it worked

```bash
claude plugin list
claude plugin details model-routing@claude-model-routing
```

The first should show `model-routing` as enabled at the current version; the second
lists its components — ten agents and two hooks. New agents also show up in the
Agent tool's list at the start of the next session.

That only proves the plugin *loaded* — it reads the definition files, so it passes
even if both hooks are dead. To confirm the hooks work, spawn a generic subagent from a
Fable or Opus session and check that the subagent ran on Sonnet. If it ran on Fable, the
model-default hook isn't taking effect.

For whether it's actually changing behavior, run this on any machine:

```bash
python3 check-delegation.py
```

For the full picture — dollars by model, main thread versus subagents, what the
expensive main thread's requests actually did, and whether delegating changed
main-thread cost per turn — run the deeper one:

```bash
python3 model-usage-audit.py            # all history
python3 model-usage-audit.py --days 30  # recent
python3 model-usage-audit.py --days 30 --summary   # five lines, safe to paste in a thread
```

For a pilot, the ask to each person is one line, no clone needed:

```bash
curl -fsSL https://raw.githubusercontent.com/brandonhall/claude-model-routing/main/model-usage-audit.py | python3 - --days 30 --summary
```

Both count each API message once (the logs repeat a message's usage once per content
block, 2–4× depending on the model) and print aggregates only. Section 3 of the audit
is the one to read first: if most top-tier main-thread spend is on requests that ran a
shell command, fetched data, or edited a file rather than requests that answered,
planned, or dispatched, the main session is a tool loop on an expensive model, and the
cheaper fix is a Sonnet main session with the expensive model held for design and
decisions — not more delegation from a Fable session.

It prints one number — what share of tokens went to assistants rather than the main
session — plus which models each side ran on. Higher is better. Run it before rollout
and again a few weeks later; if the delegated share went up, it's working.

Two things to watch in that output:

- **"Delegated" share going up** means the session note is landing.
- **Opus and Fable disappearing from the "Delegated work runs on" list** means the
  default-model hook is landing. Any expensive model still showing up under delegated
  work is a subagent that inherited it from the main session.

It reads only the local logs in `~/.claude/projects`, never prompts, file contents,
paths, or branch names, and prints only aggregate numbers.

## Prior art

Others have built the same idea for Claude Code, none of it cross-tool:
[claude-model-router-hook](https://github.com/tzachbon/claude-model-router-hook)
(routes by prompt class, but defaults implementation to Opus),
[Gearbox](https://github.com/Adityaraj0421/gearbox) (tiered agents plus an escalation
ladder and verifier — the `editor` agent and the per-project override here are borrowed
from it), and [TokenWise](https://github.com/CodeShuX/tokenwise) (routing plus a ledger
of measured savings). Anthropic tracks the native request in
[claude-code#27665](https://github.com/anthropics/claude-code/issues/27665).
