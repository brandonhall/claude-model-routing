#!/usr/bin/env python3
"""Announce every hand-off, and give an unpinned generic subagent a default model.

Two jobs, both on PreToolUse for Agent/Task:

  1. Announce. For every spawn, print one user-visible line naming the assistant and
     the model it will run on, e.g. "→ tester (sonnet): write regression tests".
     The person sees where the work went and at what price, every time, without the
     session having to remember to say so.

  2. Default. If the caller named no model and the agent is a generic built-in, add
     `model: sonnet`. Never override an explicit choice; never override a named
     agent's own `model:` frontmatter (a per-call model outranks frontmatter, so
     injecting one would silently demote a deliberately cheap agent).

Any failure here is silent and harmless: the spawn proceeds exactly as it would have.

Known dead zone: under CLAUDE_CODE_COORDINATOR_MODE the Agent tool drops the model
field entirely, so the default has no effect there. The announcement still fires.
"""

import glob
import json
import os
import re
import sys

DEFAULT_MODEL = "sonnet"
GENERIC_AGENTS = {"general-purpose", "Explore", "Plan", "claude"}
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pinned_models():
    """name -> model from this plugin's agent frontmatter."""
    out = {}
    for path in glob.glob(os.path.join(PLUGIN_ROOT, "agents", "*.md")):
        try:
            head = open(path, encoding="utf-8").read(2000)
        except OSError:
            continue
        name = re.search(r"^name:\s*(\S+)", head, re.M)
        model = re.search(r"^model:\s*(\S+)", head, re.M)
        if name and model:
            out[name.group(1)] = model.group(1)
    return out


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return

    agent = tool_input.get("subagent_type") or "general-purpose"
    short = agent.split(":")[-1]
    explicit = tool_input.get("model")
    pinned = pinned_models().get(short) if agent.startswith("model-routing:") else None

    updated = None
    if explicit:
        model, how = explicit, "named on the call"
    elif pinned:
        model, how = pinned, "pinned"
    elif agent in GENERIC_AGENTS:
        model, how = DEFAULT_MODEL, "defaulted"
        updated = dict(tool_input)
        updated["model"] = DEFAULT_MODEL
    else:
        model, how = "its own model", "another plugin's agent"

    desc = (tool_input.get("description") or "").strip()
    shown = short[:1].upper() + short[1:]
    line = f"→ {shown} ({model}, {how})" + (f": {desc}" if desc else "")

    out = {"systemMessage": line}
    if updated is not None:
        out["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "Defaulted an unpinned subagent to Sonnet.",
            "updatedInput": updated,
        }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
