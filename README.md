# Model routing

Sends routine work to faster, cheaper Claude models automatically, for everyone, with
nothing for anyone to remember or type.

No model is blocked. Anyone can still choose Opus or Fable at any time.

## What it adds

Four shared assistants that any team member's Claude can hand work off to:

| Assistant    | Runs on | Handles                                          |
| ------------ | ------- | ------------------------------------------------ |
| `finder`     | Haiku   | Locating files, docs, tickets, records           |
| `researcher` | Sonnet  | Reading external documentation and reporting back |
| `drafter`    | Sonnet  | First versions of writing or code                |
| `analyst`    | Sonnet  | Spreadsheets, data pulls, reducing long output   |

The model is fixed in each assistant's file, so this work lands on a fast, low-cost
model whether or not the person thinks about it. The expensive model stays on the
planning and judgment, which is what it's for.

It also attaches a short note to the start of every session saying when to hand work
off and when not to. Nobody has to invoke it.

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
