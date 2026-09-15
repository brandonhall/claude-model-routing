---
name: help
description: Explain the model-routing plugin from inside a session - which assistants exist, what model each runs on, what the two hooks do, and how to check it is working. Use when someone asks "what assistants do I have", "what does model-routing do", "which model will my subagent run on", or "is routing on".
---

Read `${CLAUDE_PLUGIN_ROOT}/ROUTING.md` and every file in `${CLAUDE_PLUGIN_ROOT}/agents/`,
then answer the person's question from those files. Do not answer from memory.

If they asked what the plugin does in general, give them:

1. A table of the assistants: name, the `model:` from its frontmatter, and its
   `description` trimmed to one line. Cheapest first.
2. One sentence each on the two hooks: any subagent spawned without a model gets Sonnet
   (an explicit model or a named agent is never overridden); the routing note is added
   at session start, from `.claude/routing.md` in the project if present, else the
   plugin's default.
3. How to check it is working, in two commands:
   `claude plugin list` and `claude plugin details model-routing@claude-model-routing`.
4. Where to change it: the agent files, `ROUTING.md`, and the version bump that every
   change needs.

If they asked which model a particular task would land on, name the assistant that
fits and its model, or say it would go to the generic default and therefore Sonnet.

Keep it short. Tables for the assistants, sentences for the rest, no headings.
