# Model routing

Lets people keep Opus or Fable as their main session while the actual work gets farmed
out to faster, cheaper models. Applies to everyone automatically, with nothing to
remember or type.

No model is blocked. Anyone can still choose Opus or Fable at any time — that's the
point. The expensive model stays; it just stops doing the grinding.

## What it adds

Five shared assistants that any team member's Claude can hand work off to:

| Assistant    | Runs on | Handles                                           |
| ------------ | ------- | ------------------------------------------------- |
| `finder`     | Haiku   | Locating files and strings in the filesystem      |
| `researcher` | Sonnet  | Reading external documentation and reporting back |
| `builder`    | Sonnet  | Completing a scoped piece of work end to end      |
| `analyst`    | Sonnet  | Spreadsheets, data pulls, reducing long output    |
| `checker`    | Sonnet  | Independently verifying finished work             |

The model is fixed in each assistant's file, so this work lands on a fast, low-cost
model whether or not the person thinks about it. The expensive model stays on the
planning, integration, and final call, which is what it's for.

Assistants finish their own piece and never stall waiting on a decision — they proceed
on a stated assumption and flag it. The session owns finishing the whole project, and
uses `checker` to confirm it rather than trusting its own summary.

It also attaches a short note to the start of every session that makes delegation the
default rather than the exception: the expensive session plans, dispatches, integrates,
and decides, and hands out everything else. Nobody has to invoke it.

### Subagents that aren't one of these five

Other tools spawn their own subagents — the Superpowers plugin does it in seven
different skills, for code review, plan execution, and parallel work. None of them name
a model, so those workers inherit whatever the main session is running. Delegating from
a Fable session gets you a Fable worker: you save context but not cost.

A second hook fills that gap. When a subagent is spawned **without** an explicit model,
it gets Sonnet. When one **is** named, the hook leaves it completely alone — it supplies
a default, it never overrides a choice.

Sonnet rather than Haiku because these generic spawns do real work (a code review, a
plan step), and Haiku's smaller context window is a poor fit for reading a large diff.
Haiku stays where it belongs, on `finder`.

### Why farming out wins even on small tasks

A handoff isn't free — it costs a fresh context plus a report to read back, roughly
1.5× the raw tokens. But the model prices are 3–10× apart, so the trade is lopsided:

| Path                              | Relative cost |
| --------------------------------- | ------------- |
| Fable does it directly            | 1.0×          |
| Sonnet does it, including handoff | ~0.45×        |
| Haiku does it, including handoff  | ~0.15×        |

It's better still against 5-hour usage limits, because the main session's context stays
small and every later turn in that session is cheaper too.

## Deploy

1. Push this repo somewhere the team can reach it. A private GitHub repo is fine.
2. In Claude admin settings, go to **Organization → Plugins**, add this repo as a
   plugin marketplace.
3. Set the `model-routing` plugin to **auto-install**.

Everyone picks it up on next sign-in.

For anyone using the Claude Code CLI rather than the desktop app, add this to managed
settings as well. **Both keys are needed** — the first registers the source, the second
actually turns the plugin on. With only the first, people get a prompt they can skip.

```json
{
  "extraKnownMarketplaces": {
    "claude-model-routing": {
      "source": { "source": "github", "repo": "YOUR-ORG/claude-model-routing" }
    }
  },
  "enabledPlugins": {
    "model-routing@claude-model-routing": true
  }
}
```

## Changing it

Each assistant is one short file in `plugins/model-routing/agents/`. Two lines matter:

- `model:` which engine it runs on
- `description:` when Claude should hand work to it

Edit, commit, push — **and bump `version` in
`plugins/model-routing/.claude-plugin/plugin.json`**. If the version string doesn't
change, updates are skipped and your edit never reaches anyone.

The session note is in `plugins/model-routing/hooks/session-start`.

## Checking it worked

Run `/context` in any session and look under Custom Agents. The five should be listed.

That only proves the *agents* loaded — it reads their definition files, so it passes
even if both hooks are dead. To confirm the hooks work, spawn a generic subagent from a
Fable or Opus session and check that the subagent ran on Sonnet. If it ran on Fable, the
model-default hook isn't taking effect.

For whether it's actually changing behavior, run this on any machine:

```bash
python3 check-delegation.py
```

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
