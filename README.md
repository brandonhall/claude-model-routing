# Model routing

Sends routine work to faster, cheaper Claude models automatically, for everyone, with
nothing for anyone to remember or type.

No model is blocked. Anyone can still choose Opus or Fable at any time.

## What it adds

Five shared assistants that any team member's Claude can hand work off to:

| Assistant    | Runs on | Handles                                           |
| ------------ | ------- | ------------------------------------------------- |
| `finder`     | Haiku   | Locating files, docs, tickets, records            |
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

It also attaches a short note to the start of every session covering when to hand work
off, when not to, and how to run independent pieces in parallel. Nobody has to invoke
it.

## Deploy

1. Push this repo somewhere the team can reach it. A private GitHub repo is fine.
2. In Claude admin settings, go to **Organization → Plugins**, add this repo as a
   plugin marketplace.
3. Set the `model-routing` plugin to **auto-install**.

Everyone picks it up on next sign-in.

For anyone using the Claude Code CLI rather than the desktop app, add this to managed
settings as well:

```json
{
  "extraKnownMarketplaces": {
    "claude-model-routing": {
      "source": { "source": "github", "repo": "YOUR-ORG/claude-model-routing" }
    }
  }
}
```

## Changing it

Each assistant is one short file in `plugins/model-routing/agents/`. Two lines matter:

- `model:` which engine it runs on
- `description:` when Claude should hand work to it

Edit, commit, push. Changes reach everyone on their next sign-in.

The session note is in `plugins/model-routing/hooks/session-start`.

## Checking it worked

Run `/agents` in any session. The four assistants should be listed with the models
above. If they are, it's live.
