# Model routing

Use the right model for the job. People keep Opus or Fable as their main session while
the actual work gets farmed out to faster, cheaper models. One plugin, applied to
everyone automatically, with nothing to remember or type.

No model is blocked. Anyone can still choose Opus or Fable at any time — that's the
point. The expensive model stays; it just stops doing the grinding.

## What it does

Three things, all in the one `model-routing` plugin.

### 1. Nine shared assistants pinned to cheap models

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

### 3. A standing note that makes delegation the default

[`ROUTING.md`](ROUTING.md) is attached to the start of every session. It tells the
expensive session that its job is to plan, dispatch, integrate, and decide — and to
hand out reading, drafting, running, and grinding. It also tells the session to name a
model on every worker it spawns itself, cheapest first.

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
  }
}
```

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

Belt and braces for the CLI: `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` in the `env` block of
settings does the same job as the default-model hook for `general-purpose` agents. It
does not cover `Explore` or `Plan`; the hook does.

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
lists its components — nine agents and two hooks. New agents also show up in the
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
