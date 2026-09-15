#!/usr/bin/env python3
"""Announce every hand-off, and give an unpinned generic subagent a default model.

Two jobs, both on PreToolUse for Agent/Task:

  1. Announce. For every spawn, hand the session one line naming the assistant and
     the model it will run on, e.g. "→ Tester (sonnet, pinned): write regression
     tests", as context it is told to repeat in its reply. Not a user-facing notice:
     those render collapsed in the desktop app and bury the tool row.

  2. Default. If the caller named no model and the agent is a generic built-in, add
     `model: sonnet`. Never override an explicit choice; never override a named
     agent's own `model:` frontmatter (a per-call model outranks frontmatter, so
     injecting one would silently demote a deliberately cheap agent).

How the model is labelled:
  - a `model` on the call            -> "named on the call"
  - one of this plugin's agents      -> its frontmatter pin, "pinned"; matched by the
                                        bare name as well as `model-routing:<name>`,
                                        because Claude Code resolves an unambiguous
                                        plugin agent without the prefix
  - a generic built-in, no model     -> "defaulted" (and the call is rewritten)
  - another plugin's namespaced agent-> "its own model"; left alone

Any failure here is silent and harmless: the spawn proceeds exactly as it would have.

Verified against the Claude Code 2.1.221 binary: the PreToolUse output schema accepts
`additionalContext`, and the PreToolUse hook runner delivers it to the model. An older
binary drops the line; the default still applies (`permissionDecision: "allow"` plus
`updatedInput`), so nothing routes differently. Rewriting the input requires answering
`allow`; `updatedInput` does not work with `ask`.

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
PLUGIN_NAMESPACE = "model-routing"
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frontmatter(text):
    """The fenced YAML block at the top of an agent file, or "" if there is none."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def pinned_models():
    """name -> model from this plugin's agent frontmatter."""
    out = {}
    for path in glob.glob(os.path.join(PLUGIN_ROOT, "agents", "*.md")):
        try:
            head = frontmatter(open(path, encoding="utf-8").read(4000))
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
    namespace, _, short = agent.rpartition(":")
    explicit = tool_input.get("model")
    ours = namespace in ("", PLUGIN_NAMESPACE)
    pinned = pinned_models().get(short) if ours else None

    updated = None
    if explicit:
        model, how = explicit, "named on the call"
    elif pinned:
        model, how = pinned, "pinned"
    elif agent in GENERIC_AGENTS:
        model, how = DEFAULT_MODEL, "defaulted"
        # Copy everything, then add the one field: updatedInput is validated against
        # the Agent tool's full schema, so a partial object is rejected.
        updated = dict(tool_input)
        updated["model"] = DEFAULT_MODEL
    else:
        model, how = "its own model", "another plugin's agent"

    desc = (tool_input.get("description") or "").strip()
    shown = short[:1].upper() + short[1:]
    line = f"→ {shown} ({model}, {how})" + (f": {desc}" if desc else "")

    # The line goes to the session as context, not to the person as a notice: a
    # user-facing systemMessage renders as a collapsed notice in the desktop app that
    # hides the tool row. The routing note tells the session to state the hand-off in
    # its reply, and this gives it the exact words.
    hso = {
        "hookEventName": "PreToolUse",
        "additionalContext": f"Hand-off: {line}. State this in your reply, with the reason.",
    }
    if updated is not None:
        hso["permissionDecision"] = "allow"
        hso["permissionDecisionReason"] = "Defaulted an unpinned subagent to Sonnet."
        hso["updatedInput"] = updated
    json.dump({"hookSpecificOutput": hso}, sys.stdout)


if __name__ == "__main__":
    main()
