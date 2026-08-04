#!/usr/bin/env python3
"""Give a subagent a default model when the caller didn't pick one.

Without this, a subagent spawned with no explicit model inherits whatever the main
session is running - so delegating from a Fable session gets you a Fable worker, and
the handoff saves context but not cost.

This only fills a gap. If the caller named a model, it is left alone.

Any failure here is silent and harmless: the spawn proceeds exactly as it would have.
"""

import json
import sys

DEFAULT_MODEL = "sonnet"


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # malformed input: leave the spawn untouched

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return

    # Never override an explicit choice.
    if tool_input.get("model"):
        return

    updated = dict(tool_input)
    updated["model"] = DEFAULT_MODEL

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "defer",
                "updatedInput": updated,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
