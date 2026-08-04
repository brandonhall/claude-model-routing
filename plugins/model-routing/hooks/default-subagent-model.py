#!/usr/bin/env python3
"""Give a generic subagent a default model when the caller didn't pick one.

Without this, a subagent spawned with no explicit model inherits whatever the main
session is running - so delegating from a Fable session gets you a Fable worker, and
the handoff saves context but not cost. Other plugins (Superpowers dispatches subagents
in seven skills) spawn generic workers this way.

Two rules, both important:

  1. If the caller named a model, do nothing. Never override a choice.
  2. If the caller named a *specific* agent, do nothing. A per-invocation model
     outranks the agent's own `model:` frontmatter, so injecting one here would
     silently demote an agent that had deliberately pinned a cheaper model.

That leaves exactly the case this is for: a generic worker with no model of its own.

Any failure here is silent and harmless: the spawn proceeds exactly as it would have.

Known dead zone: under CLAUDE_CODE_COORDINATOR_MODE the Agent tool drops the model
field entirely, so this hook has no effect there. Nothing to fix, just don't be
surprised by it.

Verified against the Claude Code 2.1.195 binary: `permissionDecision: "allow"` plus
`updatedInput` is applied to the Agent tool, and the Agent input schema accepts
`model` as one of sonnet/opus/haiku/fable.
"""

import json
import sys

DEFAULT_MODEL = "sonnet"

# Built-in workers that carry no model of their own. Anything else - our five, or
# any other plugin's agent - defines its own model and must be left alone.
GENERIC_AGENTS = {"general-purpose", "Explore", "Plan", "claude"}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # malformed input: leave the spawn untouched

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return

    # Rule 1: never override an explicit choice.
    if tool_input.get("model"):
        return

    # Rule 2: never override an agent's own frontmatter.
    agent = tool_input.get("subagent_type")
    if agent and agent not in GENERIC_AGENTS:
        return

    # DO NOT "simplify" this to {"model": DEFAULT_MODEL}. `updatedInput` REPLACES the
    # whole input object and is validated against the Agent tool's full schema, so a
    # partial object fails validation on the missing required fields and the spawn is
    # DENIED. Copy everything, then add the one field.
    updated = dict(tool_input)
    updated["model"] = DEFAULT_MODEL

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "Defaulted an unpinned subagent to Sonnet.",
                "updatedInput": updated,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
