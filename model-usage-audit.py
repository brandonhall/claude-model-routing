#!/usr/bin/env python3
"""Model-usage audit for Claude Code transcripts. Aggregates only.

Reads the local Claude Code logs (~/.claude/projects/**/*.jsonl, plus the desktop
app's Cowork store if present) and answers, in order:

  0. What is measurable here?      Claude Code versions seen; which fields the logs carry.
  1. Where did the money go?       By model, main session vs helpers (subagents).
  2. What is it made of?           Cache reads / writes / output; reasoning share.
  3. What did the expensive model  Tool steps (run / fetch / edit / read) vs
     actually do?                  answering, planning, deciding, delegating.
  4. Does depth cost?              Cost per request by position in the session, and
                                   the history it re-read.
  5. How big do sessions get?      Peak history per session; what the history is made
                                   of (tool output vs the assistant's own words).
  6. Does delegating help?         Main-session cost per turn by delegation share.
  7. What kinds of sessions?       Coding / notes-only / research / lookup / chat.
  8. Effort.                       Only same-model comparisons, only on requests whose
                                   logs record reasoning tokens.
  9. Cache timing.                 Modelled cost under the 5-minute vs 1-hour cache.
 10. By week.

    python3 model-usage-audit.py                    # all history, full report
    python3 model-usage-audit.py --days 30          # last 30 days
    python3 model-usage-audit.py --days 30 --summary   # a few lines, safe to paste
    python3 model-usage-audit.py --days 30 --json      # the summary as JSON

Method notes, because each one changed a conclusion once:
  - Each API message is logged once per content block with the same usage repeated,
    2-4x depending on the model. Every count here is per message id, once.
  - Reasoning ("thinking") tokens are only recorded by Claude Code 2.1.237 and newer.
    Anything involving them is computed only over requests that carry the field, and
    the coverage is printed next to the number. Never average them over records that
    lack the field; older sessions read as zero and look frugal.
  - Effort levels are compared only within one model, on covered requests, and only
    when both levels have enough of them. Across models the comparison is meaningless.
  - Dollars are Anthropic list prices applied to recorded tokens. On a subscription
    they are a proxy for usage-limit burn, not an invoice; the ratios are the point.

Never prints prompts, file paths, branch names, or code.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import statistics as st

ROOTS = [
    (os.path.expanduser("~/.claude/projects"), "code"),
    (os.path.expanduser("~/Library/Application Support/Claude/local-agent-mode-sessions"), "cowork"),
]
# $/MTok: input, output, cache_write_5m, cache_write_1h, cache_read  (list prices, 2026-09)
PRICES = [
    ("claude-fable-5-1", (10, 50, 12.5, 20, 0.25)),
    ("claude-mythos-5-1", (10, 50, 12.5, 20, 0.25)),
    ("claude-fable-5", (10, 50, 12.5, 20, 1.0)),
    ("claude-mythos-5", (10, 50, 12.5, 20, 1.0)),
    ("claude-opus-5", (5, 25, 6.25, 10, 0.5)),
    ("claude-opus-4-8", (5, 25, 6.25, 10, 0.5)),
    ("claude-opus-4-7", (5, 25, 6.25, 10, 0.5)),
    ("claude-opus-4-6", (5, 25, 6.25, 10, 0.5)),
    ("claude-opus-4-5", (5, 25, 6.25, 10, 0.5)),
    ("claude-opus-4-1", (15, 75, 18.75, 30, 1.5)),
    ("claude-opus-4", (15, 75, 18.75, 30, 1.5)),
    ("claude-sonnet-5", (2, 10, 2.5, 4, 0.2)),
    ("claude-sonnet-4-6", (3, 15, 3.75, 6, 0.3)),
    ("claude-sonnet-4-5", (3, 15, 3.75, 6, 0.3)),
    ("claude-sonnet-4", (3, 15, 3.75, 6, 0.3)),
    ("claude-haiku-4-5", (1, 5, 1.25, 2, 0.1)),
    ("claude-3-5-haiku", (0.8, 4, 1, 1.6, 0.08)),
]
TOP_TIER = ("fable", "mythos", "opus")
READ = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "ToolSearch", "TaskOutput", "Monitor", "ListAgents"}
EDIT = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
DISPATCH = {"Agent", "Task", "SendMessage", "Workflow", "Skill"}
DEPTH = [(1, 25), (26, 100), (101, 300), (301, 700), (701, 10**9)]
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max", "unset"]


def rates(model):
    for prefix, p in PRICES:
        if model.startswith(prefix):
            return p
    return None


def short(model):
    for prefix, _ in PRICES:
        if model.startswith(prefix):
            return prefix.replace("claude-", "")
    return model.replace("claude-", "")


def tier(model):
    return "top" if any(t in model for t in TOP_TIER) else ("small" if "haiku" in model else "mid")


def parts(model, u):
    """Dollar breakdown of one request: input, cache_write, cache_read, output, thinking (or None)."""
    p = rates(model)
    if not p:
        return None
    i, o, w5, w1, c = p
    cc = u.get("cache_creation") or {}
    w1t, w5t = cc.get("ephemeral_1h_input_tokens"), cc.get("ephemeral_5m_input_tokens")
    if w1t is None and w5t is None:
        w1t, w5t = u.get("cache_creation_input_tokens") or 0, 0
    think = (u.get("output_tokens_details") or {}).get("thinking_tokens")
    return dict(
        input=(u.get("input_tokens") or 0) * i / 1e6,
        cache_write=((w1t or 0) * w1 + (w5t or 0) * w5) / 1e6,
        cache_read=(u.get("cache_read_input_tokens") or 0) * c / 1e6,
        output=(u.get("output_tokens") or 0) * o / 1e6,
        thinking=(think * o / 1e6) if think is not None else None,
    )


def context_of(u):
    return (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)


def edit_cat(path):
    if not path:
        return "other"
    if "/memory/" in path or path.endswith("MEMORY.md"):
        return "memory"
    if "/tmp/" in path or "/scratchpad/" in path:
        return "scratch"
    if "/docs/" in path or path.endswith(".md"):
        return "docs"
    return "code"


def what(tools):
    if not tools:
        return "answer / plan / decide (text only)"
    if tools & DISPATCH:
        return "hand off (Agent, Skill)"
    if tools & EDIT:
        return "edit files"
    if "Bash" in tools and tools <= ({"Bash"} | READ):
        return "run commands"
    if tools <= READ:
        return "read / search files"
    if all(n.startswith("mcp__") for n in tools):
        return "fetch data (connected tools)"
    return "other tools"


def is_judgment(kind):
    return kind.startswith("answer") or kind.startswith("hand off")


def money(x):
    return f"${x:,.0f}"


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def walk_jsonl():
    for root, store in ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.endswith(".jsonl") and f != "audit.jsonl":
                    yield os.path.join(dirpath, f), root, store


def text_len(content):
    if isinstance(content, str):
        return len(content)
    n = 0
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                n += len(b.get("text") or "")
    return n


def tool_result_len(content):
    n = 0
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                n += len(c) if isinstance(c, str) else text_len(c)
    return n


def collect(days):
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat() if days else None
    msgs = {}
    sessions = {}
    tool_edits = collections.defaultdict(collections.Counter)
    versions = collections.Counter()
    files = 0
    first_day, last_day = None, None

    def session(key):
        s = sessions.get(key)
        if s is None:
            s = sessions[key] = dict(
                turns=0, main_req=0, sub_req=0, main_cost=0.0, sub_cost=0.0,
                main_models=collections.Counter(), tools=collections.Counter(),
                main_prompt_tok=0, peak_ctx=0, pos=0,
                chars=collections.Counter(),  # tool_result / assistant_text / user_text
            )
        return s

    for path, root, store in walk_jsonl():
        files += 1
        rel = os.path.relpath(path, root).split(os.sep)
        sub_file = (len(rel) > 2) if store == "code" else ("agent-" in os.path.basename(path))
        parent = rel[1] if (store == "code" and len(rel) > 2) else None
        with open(path, "rb") as fh:
            for raw in fh:
                if b'"type":"assistant"' not in raw and b'"type":"user"' not in raw:
                    continue
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                ts = d.get("timestamp") or ""
                if cutoff and ts and ts < cutoff:
                    continue
                key = parent or d.get("sessionId") or os.path.basename(path)[:-6]
                s = session(key)
                is_sub = bool(sub_file or d.get("isSidechain") or d.get("agentId"))
                m = d.get("message") or {}
                content = m.get("content")
                if d.get("type") == "user":
                    if is_sub or d.get("isMeta"):
                        continue
                    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                        s["chars"]["tool output"] += tool_result_len(content)
                        continue
                    if isinstance(content, str) or (isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in content)):
                        s["turns"] += 1
                        s["chars"]["what the person typed"] += text_len(content)
                    continue
                model = m.get("model") or ""
                if not model or model.startswith("<"):
                    continue
                mid = m.get("id") or d.get("requestId") or d.get("uuid")
                e = msgs.get(mid)
                if e is None:
                    if ts[:10]:
                        first_day = min(first_day or ts[:10], ts[:10])
                        last_day = max(last_day or ts[:10], ts[:10])
                    versions[d.get("version") or "?"] += 1
                    u = m.get("usage") or {}
                    e = msgs[mid] = dict(
                        model=model, usage=u, sub=is_sub, key=key, tools=set(),
                        effort=d.get("effort") or "unset", day=ts[:10], ts=ts, pos=0,
                    )
                    if not is_sub:
                        s["pos"] += 1
                        e["pos"] = s["pos"]
                        s["peak_ctx"] = max(s["peak_ctx"], context_of(u))
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and not is_sub:
                            s["chars"]["what the assistant wrote"] += len(b.get("text") or "")
                        if b.get("type") == "tool_use":
                            name = b.get("name") or "?"
                            e["tools"].add(name)
                            if not is_sub:
                                s["tools"][name] += 1
                                if name in EDIT:
                                    inp = b.get("input") or {}
                                    tool_edits[key][edit_cat(inp.get("file_path") or inp.get("notebook_path"))] += 1

    for e in msgs.values():
        p = parts(e["model"], e["usage"])
        e["parts"] = p
        e["cost"] = sum(v for k, v in p.items() if k != "thinking" and v is not None) if p else 0.0
        s = sessions[e["key"]]
        sm = short(e["model"])
        if e["sub"]:
            s["sub_req"] += 1
            s["sub_cost"] += e["cost"]
        else:
            s["main_req"] += 1
            s["main_cost"] += e["cost"]
            s["main_models"][sm] += e["cost"]
            s["main_prompt_tok"] += context_of(e["usage"])
    for key, s in sessions.items():
        ed = tool_edits.get(key, {})
        total_tools = sum(s["tools"].values())
        if ed.get("code", 0):
            s["kind"] = "coding (edits repo files)"
        elif sum(ed.values()):
            s["kind"] = "notes only (docs, memory, scratch)"
        elif total_tools == 0:
            s["kind"] = "chat (no tools)"
        elif total_tools <= 15:
            s["kind"] = "quick lookup (<=15 tool calls)"
        else:
            s["kind"] = "research (read-only, >15 tool calls)"
        s["main_model"] = s["main_models"].most_common(1)[0][0] if s["main_models"] else "?"
    return dict(msgs=msgs, sessions=sessions, files=files, versions=versions, first=first_day, last=last_day)


def compute(data):
    """Everything the report and the summary need, as plain numbers."""
    L = [e for e in data["msgs"].values() if e["parts"]]
    S = data["sessions"]
    out = {}
    total = sum(e["cost"] for e in L) or 1.0
    out["total"] = total
    out["requests"] = len(L)
    out["sessions"] = len(S)
    covered = [e for e in L if e["parts"]["thinking"] is not None]
    out["coverage"] = len(covered) / len(L) if L else 0.0

    main = [e for e in L if not e["sub"]]
    subs = [e for e in L if e["sub"]]
    out["main_cost"] = sum(e["cost"] for e in main)
    out["sub_cost"] = sum(e["cost"] for e in subs)
    out["sub_top_cost"] = sum(e["cost"] for e in subs if tier(e["model"]) == "top")
    by_tier = collections.Counter()
    for e in main:
        by_tier[tier(e["model"])] += e["cost"]
    out["main_by_tier"] = by_tier
    mm = collections.Counter()
    for e in main:
        mm[short(e["model"])] += e["cost"]
    out["main_lead_model"] = mm.most_common(1)[0][0] if mm else "?"

    top_main = [e for e in main if tier(e["model"]) == "top"]
    out["top_main_cost"] = sum(e["cost"] for e in top_main)
    out["top_main_tool_cost"] = sum(e["cost"] for e in top_main if not is_judgment(what(e["tools"])))
    tc = [e for e in top_main if e["parts"]["thinking"] is not None]
    out["top_main_covered_cost"] = sum(e["cost"] for e in tc)
    out["top_main_thinking_cost"] = sum(e["parts"]["thinking"] for e in tc)
    out["top_main_coverage"] = len(tc) / len(top_main) if top_main else 0.0
    out["top_main_deep_cost"] = sum(e["cost"] for e in top_main if e["pos"] > 100)

    peaks = [s["peak_ctx"] for s in S.values() if s["main_req"] >= 5]
    out["peak_median"] = st.median(peaks) if peaks else 0
    out["peak_p90"] = sorted(peaks)[int(0.9 * (len(peaks) - 1))] if peaks else 0
    out["peak_over_200k"] = sum(p > 200_000 for p in peaks) / len(peaks) if peaks else 0.0
    out["peak_n"] = len(peaks)
    chars = collections.Counter()
    for s in S.values():
        chars.update(s["chars"])
    out["chars"] = chars
    return out


def report(data, days):
    L = [e for e in data["msgs"].values() if e["parts"]]
    S = data["sessions"]
    c = compute(data)
    total = c["total"]
    window = f"last {days} days" if days else "all history"
    print(f"\nMODEL USAGE AUDIT ({window})")
    print(f"{c['sessions']} sessions, {c['requests']} API requests, {data['files']} transcript files, {data['first']} to {data['last']}, {money(total)} list-equivalent")

    print("\n0. WHAT IS MEASURABLE HERE")
    vs = data["versions"].most_common(6)
    print("   Claude Code versions (requests): " + ", ".join(f"{v} ({n})" for v, n in vs))
    print(f"   requests whose logs record reasoning tokens: {pct(c['coverage'] * 100, 100)}  (the field arrived in 2.1.237; anything about reasoning below uses only these)")

    print("\n1. WHERE THE MONEY WENT  (main session vs helpers)")
    by = collections.defaultdict(lambda: dict(n=0, main=0.0, sub=0.0))
    for e in L:
        b = by[short(e["model"])]
        b["n"] += 1
        b["sub" if e["sub"] else "main"] += e["cost"]
    print(f"   {'model':<12}{'requests':>9}{'$ main':>10}{'$ helpers':>11}{'$ total':>10}{'share':>8}")
    for m, b in sorted(by.items(), key=lambda kv: -(kv[1]["main"] + kv[1]["sub"])):
        t = b["main"] + b["sub"]
        if t < 1:
            continue
        print(f"   {m:<12}{b['n']:>9}{money(b['main']):>10}{money(b['sub']):>11}{money(t):>10}{100 * t / total:>7.1f}%")
    print(f"   main session {money(c['main_cost'])} ({pct(c['main_cost'], total)}); helpers {money(c['sub_cost'])} ({pct(c['sub_cost'], total)}), of which on top-tier models {pct(c['sub_top_cost'], c['sub_cost'])}")

    print("\n2. WHAT THE MAIN-SESSION DOLLARS ARE MADE OF")
    comp = collections.defaultdict(collections.Counter)
    cov = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])  # n, n_covered, covered cost, thinking $
    n_main = collections.Counter()
    ptok = collections.Counter()
    for e in L:
        if e["sub"]:
            continue
        sm = short(e["model"])
        n_main[sm] += 1
        for k, v in e["parts"].items():
            if k != "thinking":
                comp[sm][k] += v
        ptok[sm] += context_of(e["usage"])
        cov[sm][0] += 1
        if e["parts"]["thinking"] is not None:
            cov[sm][1] += 1
            cov[sm][2] += e["cost"]
            cov[sm][3] += e["parts"]["thinking"]
    for sm, cc in sorted(comp.items(), key=lambda kv: -sum(kv[1].values())):
        t = sum(cc.values())
        if t < 50:
            continue
        n, nc, ccost, th = cov[sm]
        think = f"reasoning {100 * th / ccost:.1f}% of cost on the {100 * nc / n:.0f}% of requests that record it" if nc else "reasoning not recorded"
        print(f"   {sm:<12} re-reads {100 * cc['cache_read'] / t:3.0f}%  new history {100 * cc['cache_write'] / t:3.0f}%  output {100 * cc['output'] / t:3.0f}%   avg history per request {ptok[sm] / n_main[sm] / 1000:4.0f}K tok   {money(t)}   ({think})")

    print("\n3. WHAT THE EXPENSIVE MODEL'S MAIN-SESSION REQUESTS DID")
    wf = collections.defaultdict(lambda: [0, 0.0])
    for e in L:
        if e["sub"] or tier(e["model"]) != "top":
            continue
        w = wf[what(e["tools"])]
        w[0] += 1
        w[1] += e["cost"]
    tt = sum(w[1] for w in wf.values()) or 1
    print(f"   {'what the request did':<38}{'req':>7}{'$':>9}{'share':>7}")
    for k, w in sorted(wf.items(), key=lambda kv: -kv[1][1]):
        print(f"   {k:<38}{w[0]:>7}{money(w[1]):>9}{100 * w[1] / tt:>6.0f}%")
    judg = tt - c["top_main_tool_cost"]
    think_line = f"reasoning tokens {pct(c['top_main_thinking_cost'], c['top_main_covered_cost'])} of cost on the {c['top_main_coverage'] * 100:.0f}% of these requests that record them" if c["top_main_covered_cost"] else "reasoning not recorded"
    print(f"   -> tool steps {pct(c['top_main_tool_cost'], tt)}; answering / planning / deciding / handing off {pct(judg, tt)}; {think_line}")

    print("\n4. DOES DEPTH COST?  (expensive model, main session, by position in the session)")
    agg = {b: [0, 0.0, 0] for b in DEPTH}
    for e in L:
        if e["sub"] or tier(e["model"]) != "top":
            continue
        for b in DEPTH:
            if b[0] <= e["pos"] <= b[1]:
                agg[b][0] += 1
                agg[b][1] += e["cost"]
                agg[b][2] += context_of(e["usage"])
                break
    dtot = sum(a[1] for a in agg.values()) or 1
    print(f"   {'request # in session':<22}{'requests':>9}{'avg $/req':>10}{'history re-read':>17}{'share of $':>11}")
    for b in DEPTH:
        n, d, ctx = agg[b]
        if not n:
            continue
        lab = f"{b[0]}-{b[1]}" if b[1] < 10**9 else f"{b[0]}+"
        print(f"   {lab:<22}{n:>9}{d / n:>10.2f}{ctx / n / 1000:>15.0f}K{100 * d / dtot:>10.0f}%")
    print(f"   -> requests past #100 in their session: {pct(c['top_main_deep_cost'], dtot)} of expensive-model main-session spend")

    print("\n5. HOW BIG SESSIONS GET  (peak history per session, sessions with >=5 main requests)")
    if c["peak_n"]:
        print(f"   {c['peak_n']} sessions: median peak {c['peak_median'] / 1000:.0f}K tokens, p90 {c['peak_p90'] / 1000:.0f}K, {c['peak_over_200k'] * 100:.0f}% of sessions exceed 200K at some point")
    ch = c["chars"]
    cht = sum(ch.values()) or 1
    print("   what the history is made of (characters, main session): " + ", ".join(f"{k} {100 * v / cht:.0f}%" for k, v in ch.most_common()))

    print("\n6. DOES DELEGATING MORE LOWER MAIN-SESSION COST PER TURN?  (coding + notes sessions, >=5 turns, >=30 main requests)")
    rows = [s for s in S.values() if s["kind"].startswith(("coding", "notes")) and s["turns"] >= 5 and s["main_req"] >= 30]
    buckets = collections.defaultdict(list)
    for s in rows:
        sh = s["sub_req"] / (s["main_req"] + s["sub_req"])
        buckets["A: 0% delegated" if sh == 0 else "B: 1-30%" if sh < .3 else "C: 30-60%" if sh < .6 else "D: 60%+"].append(s)
    print(f"   {'bucket':<18}{'n':>4}{'main history':>14}{'main req/turn':>15}{'main $/turn':>13}{'total $/turn':>14}{'median turns':>14}")
    for b in sorted(buckets):
        B = buckets[b]
        if len(B) < 3:
            continue
        print(f"   {b:<18}{len(B):>4}{st.median(s['main_prompt_tok'] / s['main_req'] / 1000 for s in B):>13.0f}K{st.median(s['main_req'] / s['turns'] for s in B):>15.1f}{st.median(s['main_cost'] / s['turns'] for s in B):>13.2f}{st.median((s['main_cost'] + s['sub_cost']) / s['turns'] for s in B):>14.2f}{st.median(s['turns'] for s in B):>14.0f}")
    if len(rows) > 10:
        xs = [s["sub_req"] / (s["main_req"] + s["sub_req"]) for s in rows]
        ys = [s["main_prompt_tok"] / s["main_req"] for s in rows]
        mx, my = st.mean(xs), st.mean(ys)
        den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        if den:
            print(f"   correlation(delegation share, main history size) over {len(rows)} sessions: r = {sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den:+.2f}   (a negative number would mean delegating shrinks the main session)")

    print("\n7. SESSION KINDS  ($ including that session's helpers)")
    kinds = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0]))
    for s in S.values():
        b = kinds[s["kind"]][s["main_model"]]
        b[0] += 1
        b[1] += s["main_cost"] + s["sub_cost"]
    for k in ["coding (edits repo files)", "notes only (docs, memory, scratch)", "research (read-only, >15 tool calls)", "quick lookup (<=15 tool calls)", "chat (no tools)"]:
        kt = sum(v[1] for v in kinds[k].values())
        print(f"   {k:<40} {money(kt):>9} ({100 * kt / total:4.1f}%)   " + ", ".join(f"{m} {n}x {money(cst)}" for m, (n, cst) in sorted(kinds[k].items(), key=lambda kv: -kv[1][1]) if n))

    print("\n8. EFFORT  (same model only, requests that record reasoning tokens only)")
    eff = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])  # n covered, thinking tokens, output tokens, n all
    for e in L:
        if e["sub"] or tier(e["model"]) != "top":
            continue
        k = (short(e["model"]), e["effort"])
        eff[k][3] += 1
        th = (e["usage"].get("output_tokens_details") or {}).get("thinking_tokens")
        if th is not None:
            eff[k][0] += 1
            eff[k][1] += th
            eff[k][2] += e["usage"].get("output_tokens") or 0
    models = sorted({k[0] for k in eff})
    any_pair = False
    for mdl in models:
        levels = [(lv, eff[(mdl, lv)]) for lv in EFFORT_ORDER if (mdl, lv) in eff and eff[(mdl, lv)][0] >= 200]
        if len(levels) < 2:
            continue
        any_pair = True
        print(f"   {mdl}: " + "; ".join(f"{lv}: {v[1] / v[0]:.0f} reasoning tok/req, {v[2] / v[0]:.0f} output tok/req over {v[0]} requests" for lv, v in levels))
    if not any_pair:
        print("   no same-model comparison available (fewer than 200 covered requests at two effort levels for any one model) — do not draw conclusions about effort from this machine")
    print("   effort levels in use: " + ", ".join(f"{lv} {sum(v[3] for k, v in eff.items() if k[1] == lv)} req" for lv in EFFORT_ORDER if any(k[1] == lv for k in eff)))

    print("\n9. CACHE TIMING  (modelled: what the same requests would have cost with a 5-minute cache instead of the 1-hour one Claude Code uses)")
    per = collections.defaultdict(lambda: [0.0, 0.0, 0])
    gaps = []
    by_session = collections.defaultdict(list)
    for e in L:
        if not e["sub"] and e["ts"]:
            by_session[e["key"]].append(e)
    for key, es in by_session.items():
        es.sort(key=lambda e: e["ts"])
        prev = None
        for e in es:
            try:
                t = dt.datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
            except Exception:
                continue
            gap = (t - prev).total_seconds() if prev else 0
            prev = t
            if gap:
                gaps.append(gap)
            p = rates(e["model"])
            if not p:
                continue
            i, o, w5, w1, cr = p
            u = e["usage"]
            cw, rd = u.get("cache_creation_input_tokens") or 0, u.get("cache_read_input_tokens") or 0
            base = ((u.get("input_tokens") or 0) * i + (u.get("output_tokens") or 0) * o) / 1e6
            c1h = base + (cw * w1 + rd * cr) / 1e6
            c5m = base + (((cw + rd) * w5) / 1e6 if gap > 300 else (cw * w5 + rd * cr) / 1e6)
            sm = short(e["model"])
            per[sm][0] += c1h
            per[sm][1] += c5m
            per[sm][2] += 1
    if gaps:
        gaps.sort()
        n = len(gaps)
        print(f"   gap between consecutive main-session requests: median {gaps[n // 2]:.0f}s, p90 {gaps[int(0.9 * (n - 1))]:.0f}s, {100 * sum(g > 300 for g in gaps) / n:.1f}% over 5 minutes")
    for sm, (a, b, n) in sorted(per.items(), key=lambda kv: -kv[1][0]):
        if a < 50:
            continue
        print(f"   {sm:<12} 1-hour cache {money(a):>9}   5-minute cache {money(b):>9}   ({'+' if b >= a else ''}{100 * (b - a) / a:.0f}%)")

    print("\n10. BY WEEK  ($, top models)")
    top5 = [m for m, _ in sorted(by.items(), key=lambda kv: -(kv[1]["main"] + kv[1]["sub"]))[:5]]
    wk = collections.defaultdict(collections.Counter)
    for e in L:
        if not e["day"]:
            continue
        d = dt.date.fromisoformat(e["day"])
        wk[(d - dt.timedelta(days=d.weekday())).isoformat()][short(e["model"])] += e["cost"]
    print(f"   {'week of':<12}" + "".join(f"{m:>12}" for m in top5) + f"{'total':>10}")
    for w in sorted(wk):
        if sum(wk[w].values()) < 20:
            continue
        print(f"   {w:<12}" + "".join(f"{money(wk[w][m]):>12}" for m in top5) + f"{money(sum(wk[w].values())):>10}")
    print("\nDollars are Anthropic list prices applied to the recorded token counts; on a subscription they are a proxy for usage-limit burn, not an invoice. Every count is per API message, once.\n")


def summary_numbers(data, days):
    c = compute(data)
    return dict(
        window=(f"last {days} days" if days else "all history"),
        sessions=c["sessions"], requests=c["requests"], first_day=data["first"], last_day=data["last"],
        total_usd=round(c["total"]), main_lead_model=c["main_lead_model"],
        main_usd=round(c["main_cost"]), main_top_tier_usd=round(c["main_by_tier"]["top"]),
        top_main_tool_step_share=round(c["top_main_tool_cost"] / c["top_main_cost"], 3) if c["top_main_cost"] else None,
        top_main_reasoning_share=round(c["top_main_thinking_cost"] / c["top_main_covered_cost"], 3) if c["top_main_covered_cost"] else None,
        reasoning_coverage=round(c["top_main_coverage"], 3),
        top_main_past_100_share=round(c["top_main_deep_cost"] / c["top_main_cost"], 3) if c["top_main_cost"] else None,
        peak_history_median_tokens=round(c["peak_median"]), sessions_over_200k_share=round(c["peak_over_200k"], 3),
        helper_usd=round(c["sub_cost"]), helper_top_tier_share=round(c["sub_top_cost"] / c["sub_cost"], 3) if c["sub_cost"] else None,
        versions=dict(data["versions"].most_common(4)),
    )


def summary(data, days):
    n = summary_numbers(data, days)
    c = compute(data)
    print(f"model-usage-audit ({n['window']}, {n['sessions']} sessions, {n['first_day']} to {n['last_day']})")
    print(f"  total {money(n['total_usd'])} list-equivalent; main session mostly on {n['main_lead_model']}")
    print(f"  expensive-model spend in the main session: {money(c['top_main_cost'])} ({pct(c['top_main_cost'], c['total'])} of total), of which {pct(c['top_main_tool_cost'], c['top_main_cost'])} was tool steps and {pct(c['top_main_deep_cost'], c['top_main_cost'])} came after request #100 of a session")
    rs = f"{100 * c['top_main_thinking_cost'] / c['top_main_covered_cost']:.1f}% of that was reasoning tokens (measured on the {c['top_main_coverage'] * 100:.0f}% of requests that record them)" if c["top_main_covered_cost"] else "reasoning tokens not recorded by this Claude Code version"
    print(f"  {rs}")
    print(f"  sessions peak at a median {c['peak_median'] / 1000:.0f}K tokens of history; {c['peak_over_200k'] * 100:.0f}% exceed 200K")
    print(f"  helper (subagent) spend: {money(c['sub_cost'])} ({pct(c['sub_cost'], c['total'])} of total), of which {pct(c['sub_top_cost'], c['sub_cost'])} ran on expensive models")
    print(f"  requests {n['requests']}, each API message counted once; list prices 2026-09; Claude Code " + ", ".join(n["versions"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=0, help="0 = all history")
    ap.add_argument("--summary", action="store_true", help="a few lines, safe to paste into a thread")
    ap.add_argument("--json", action="store_true", help="the summary numbers as JSON")
    a = ap.parse_args()
    data = collect(a.days)
    if a.json:
        print(json.dumps(summary_numbers(data, a.days), indent=2))
    elif a.summary:
        summary(data, a.days)
    else:
        report(data, a.days)
