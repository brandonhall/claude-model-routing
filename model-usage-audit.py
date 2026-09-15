#!/usr/bin/env python3
import argparse, collections, datetime as dt, json, os, statistics as st
ROOTS = [
    (os.path.expanduser('~/.claude/projects'), 'code'),
    (os.path.expanduser('~/Library/Application Support/Claude/local-agent-mode-sessions'), 'cowork'),
]
PRICES = [
    ('claude-fable-5-1', (10, 50, 12.5, 20, 0.25)),
    ('claude-mythos-5-1', (10, 50, 12.5, 20, 0.25)),
    ('claude-fable-5',   (10, 50, 12.5, 20, 1.0)),
    ('claude-mythos-5',  (10, 50, 12.5, 20, 1.0)),
    ('claude-opus-5',    (5, 25, 6.25, 10, 0.5)),
    ('claude-opus-4-8',  (5, 25, 6.25, 10, 0.5)),
    ('claude-opus-4-7',  (5, 25, 6.25, 10, 0.5)),
    ('claude-opus-4-6',  (5, 25, 6.25, 10, 0.5)),
    ('claude-opus-4-5',  (5, 25, 6.25, 10, 0.5)),
    ('claude-opus-4-1',  (15, 75, 18.75, 30, 1.5)),
    ('claude-opus-4',    (15, 75, 18.75, 30, 1.5)),
    ('claude-sonnet-5',  (2, 10, 2.5, 4, 0.2)),
    ('claude-sonnet-4-6',(3, 15, 3.75, 6, 0.3)),
    ('claude-sonnet-4-5',(3, 15, 3.75, 6, 0.3)),
    ('claude-sonnet-4',  (3, 15, 3.75, 6, 0.3)),
    ('claude-haiku-4-5', (1, 5, 1.25, 2, 0.1)),
    ('claude-3-5-haiku', (0.8, 4, 1, 1.6, 0.08)),
]
TOP_TIER = ('fable', 'mythos', 'opus')
READ = {'Read', 'Grep', 'Glob', 'LS', 'WebFetch', 'WebSearch', 'ToolSearch', 'TaskOutput', 'Monitor', 'ListAgents'}
EDIT = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
DISPATCH = {'Agent', 'Task', 'SendMessage', 'Workflow', 'Skill'}
def rates(model):
    for prefix, p in PRICES:
        if model.startswith(prefix): return p
    return None
def short(model):
    for prefix, _ in PRICES:
        if model.startswith(prefix): return prefix.replace('claude-', '')
    return model.replace('claude-', '')
def parts(model, u):
    p = rates(model)
    if not p: return None
    i, o, w5, w1, c = p
    cc = u.get('cache_creation') or {}
    w1t, w5t = cc.get('ephemeral_1h_input_tokens'), cc.get('ephemeral_5m_input_tokens')
    if w1t is None and w5t is None: w1t, w5t = u.get('cache_creation_input_tokens') or 0, 0
    think = ((u.get('output_tokens_details') or {}).get('thinking_tokens') or 0)
    return dict(input=(u.get('input_tokens') or 0) * i / 1e6,
                cache_write=((w1t or 0) * w1 + (w5t or 0) * w5) / 1e6,
                cache_read=(u.get('cache_read_input_tokens') or 0) * c / 1e6,
                output=(u.get('output_tokens') or 0) * o / 1e6,
                thinking=think * o / 1e6)
def edit_cat(path):
    if not path: return 'other'
    if '/memory/' in path or path.endswith('MEMORY.md'): return 'memory'
    if '/tmp/' in path or '/scratchpad/' in path: return 'scratch'
    if '/docs/' in path or path.endswith('.md'): return 'docs'
    return 'code'
def what(tools):
    if not tools: return 'text only (answer / plan / decide)'
    if tools & DISPATCH: return 'dispatch (Agent, Skill)'
    if tools & EDIT: return 'edit files'
    if 'Bash' in tools and tools <= ({'Bash'} | READ): return 'run commands (Bash)'
    if tools <= READ: return 'read / search files'
    if all(n.startswith('mcp__') for n in tools): return 'MCP calls (fetch data)'
    return 'other tools'
def money(x): return f"${x:,.0f}"
def walk_jsonl():
    for root, store in ROOTS:
        if not os.path.isdir(root): continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.endswith('.jsonl') and f != 'audit.jsonl':
                    yield os.path.join(dirpath, f), root, store
def collect(days):
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat() if days else None
    msgs = {}; sessions = {}; tool_edits = collections.defaultdict(collections.Counter); files = 0
    for path, root, store in walk_jsonl():
        files += 1
        rel = os.path.relpath(path, root).split(os.sep)
        sub_file = (len(rel) > 2) if store == 'code' else ('agent-' in os.path.basename(path))
        parent = rel[1] if (store == 'code' and len(rel) > 2) else None
        with open(path, 'rb') as fh:
            for raw in fh:
                if b'"type":"assistant"' not in raw and b'"type":"user"' not in raw: continue
                try: d = json.loads(raw)
                except Exception: continue
                ts = d.get('timestamp') or ''
                if cutoff and ts and ts < cutoff: continue
                key = parent or d.get('sessionId') or os.path.basename(path)[:-6]
                s = sessions.get(key)
                if s is None:
                    s = sessions[key] = dict(turns=0, main_req=0, sub_req=0, main_cost=0.0, sub_cost=0.0,
                                             main_models=collections.Counter(), sub_models=collections.Counter(),
                                             tools=collections.Counter(), main_prompt_tok=0, start=None)
                if ts and (s['start'] is None or ts < s['start']): s['start'] = ts
                is_sub = bool(sub_file or d.get('isSidechain') or d.get('agentId'))
                m = d.get('message') or {}; content = m.get('content')
                if d.get('type') == 'user':
                    if is_sub or d.get('isMeta'): continue
                    if isinstance(content, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content): continue
                    if isinstance(content, str) or (isinstance(content, list) and any(isinstance(b, dict) and b.get('type') == 'text' for b in content)):
                        s['turns'] += 1
                    continue
                model = m.get('model') or ''
                if not model or model.startswith('<'): continue
                mid = m.get('id') or d.get('requestId') or d.get('uuid')
                e = msgs.get(mid)
                if e is None:
                    e = msgs[mid] = dict(model=model, usage=m.get('usage') or {}, sub=is_sub, key=key, tools=set(),
                                         effort=d.get('effort') or 'default', day=ts[:10])
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get('type') == 'tool_use':
                            name = b.get('name') or '?'
                            e['tools'].add(name)
                            if not is_sub:
                                s['tools'][name] += 1
                                if name in EDIT:
                                    inp = b.get('input') or {}
                                    tool_edits[key][edit_cat(inp.get('file_path') or inp.get('notebook_path'))] += 1
    for e in msgs.values():
        p = parts(e['model'], e['usage'])
        e['cost'] = sum(v for k, v in p.items() if k != 'thinking') if p else 0.0
        e['parts'] = p
        s = sessions[e['key']]; sm = short(e['model'])
        if e['sub']:
            s['sub_req'] += 1; s['sub_cost'] += e['cost']; s['sub_models'][sm] += e['cost']
        else:
            s['main_req'] += 1; s['main_cost'] += e['cost']; s['main_models'][sm] += e['cost']
            u = e['usage']; s['main_prompt_tok'] += (u.get('cache_read_input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0) + (u.get('input_tokens') or 0)
    for key, s in sessions.items():
        e = tool_edits.get(key, {}); total_tools = sum(s['tools'].values())
        if e.get('code', 0): s['kind'] = 'coding (edits repo files)'
        elif sum(e.values()): s['kind'] = 'advisory (writes notes/docs/memory only)'
        elif total_tools == 0: s['kind'] = 'chat (no tools)'
        elif total_tools <= 15: s['kind'] = 'quick lookup (<=15 tool calls)'
        else: s['kind'] = 'research (read-only, >15 tool calls)'
        s['main_model'] = s['main_models'].most_common(1)[0][0] if s['main_models'] else '?'
    return msgs, sessions, files
def report(msgs, sessions, files, days):
    L = [e for e in msgs.values() if e['parts']]
    total = sum(e['cost'] for e in L)
    print(f"\nMODEL USAGE AUDIT ({'last %d days' % days if days else 'all history'})")
    print(f"{len(sessions)} sessions, {len(L)} API requests, {files} transcript files, {money(total)} API-equivalent\n")
    print("1. BY MODEL")
    by = collections.defaultdict(lambda: dict(n=0, main=0.0, sub=0.0))
    for e in L:
        b = by[short(e['model'])]; b['n'] += 1; b['sub' if e['sub'] else 'main'] += e['cost']
    print(f"   {'model':<12}{'requests':>9}{'$ main':>10}{'$ subagent':>12}{'$ total':>10}{'share':>8}")
    for m, b in sorted(by.items(), key=lambda kv: -(kv[1]['main'] + kv[1]['sub'])):
        t = b['main'] + b['sub']
        if t < 1: continue
        print(f"   {m:<12}{b['n']:>9}{money(b['main']):>10}{money(b['sub']):>12}{money(t):>10}{100*t/total:>7.1f}%")
    print("\n2. WHERE THE DOLLARS GO INSIDE EACH MODEL (main thread)")
    comp = collections.defaultdict(collections.Counter); n_main = collections.Counter(); ptok = collections.Counter()
    for e in L:
        if e['sub']: continue
        sm = short(e['model']); n_main[sm] += 1
        for k, v in e['parts'].items(): comp[sm][k] += v
        u = e['usage']; ptok[sm] += (u.get('cache_read_input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0) + (u.get('input_tokens') or 0)
    for sm, c in sorted(comp.items(), key=lambda kv: -sum(v for k, v in kv[1].items() if k != 'thinking')):
        t = sum(v for k, v in c.items() if k != 'thinking')
        if t < 50: continue
        print(f"   {sm:<12} cache reads {100*c['cache_read']/t:3.0f}%  cache writes {100*c['cache_write']/t:3.0f}%  output {100*c['output']/t:3.0f}%  (thinking alone {100*c['thinking']/t:3.1f}%)   avg prompt {ptok[sm]/n_main[sm]/1000:4.0f}K tok   {money(t)}")
    print("\n3. WHAT THE TOP-TIER MAIN THREAD'S REQUESTS DID (Fable/Opus, main thread only)")
    wf = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for e in L:
        if e['sub'] or not any(t in e['model'] for t in TOP_TIER): continue
        w = wf[what(e['tools'])]; w[0] += 1; w[1] += e['cost']; w[2] += e['parts']['thinking']
    tt = sum(w[1] for w in wf.values()) or 1
    print(f"   {'what the request did':<38}{'req':>7}{'$':>9}{'share':>7}")
    for k, w in sorted(wf.items(), key=lambda kv: -kv[1][1]):
        print(f"   {k:<38}{w[0]:>7}{money(w[1]):>9}{100*w[1]/tt:>6.0f}%")
    judgment = sum(w[1] for k, w in wf.items() if k.startswith('text only') or k.startswith('dispatch'))
    print(f"   -> judgment (text-only + dispatch): {money(judgment)} = {100*judgment/tt:.0f}%;  everything else: {100*(tt-judgment)/tt:.0f}%;  thinking tokens alone: {money(sum(w[2] for w in wf.values()))} = {100*sum(w[2] for w in wf.values())/tt:.1f}%")
    print("\n4. DOES DELEGATING MORE LOWER MAIN-THREAD COST PER TURN?")
    rows = [s for s in sessions.values() if s['kind'].startswith(('coding', 'advisory')) and s['turns'] >= 5 and s['main_req'] >= 30]
    buckets = collections.defaultdict(list)
    for s in rows:
        sh = s['sub_req'] / (s['main_req'] + s['sub_req'])
        buckets['A: 0% delegated' if sh == 0 else 'B: 1-30%' if sh < .3 else 'C: 30-60%' if sh < .6 else 'D: 60%+'].append(s)
    print(f"   {'bucket':<18}{'n':>4}{'main ctx':>10}{'main req/turn':>15}{'main $/turn':>13}{'total $/turn':>14}{'median turns':>14}")
    for b in sorted(buckets):
        S = buckets[b]
        if len(S) < 3: continue
        print(f"   {b:<18}{len(S):>4}{st.median(s['main_prompt_tok']/s['main_req']/1000 for s in S):>9.0f}K{st.median(s['main_req']/s['turns'] for s in S):>15.1f}{st.median(s['main_cost']/s['turns'] for s in S):>13.2f}{st.median((s['main_cost']+s['sub_cost'])/s['turns'] for s in S):>14.2f}{st.median(s['turns'] for s in S):>14.0f}")
    if len(rows) > 10:
        import math
        xs = [s['sub_req'] / (s['main_req'] + s['sub_req']) for s in rows]; ys = [s['main_prompt_tok']/s['main_req'] for s in rows]
        mx, my = st.mean(xs), st.mean(ys)
        den = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
        if den: print(f"   correlation(delegation share, main context size) over {len(rows)} sessions: r = {sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den:+.2f}")
    print("\n5. SESSION KIND x MAIN MODEL")
    kinds = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0]))
    for s in sessions.values():
        b = kinds[s['kind']][s['main_model']]; b[0] += 1; b[1] += s['main_cost'] + s['sub_cost']
    for k in ['coding (edits repo files)', 'advisory (writes notes/docs/memory only)', 'research (read-only, >15 tool calls)', 'quick lookup (<=15 tool calls)', 'chat (no tools)']:
        kt = sum(v[1] for v in kinds[k].values())
        print(f"   {k:<42} {money(kt):>9} ({100*kt/total:4.1f}%)   " + ', '.join(f"{m} {n}x {money(c)}" for m, (n, c) in sorted(kinds[k].items(), key=lambda kv: -kv[1][1]) if n))
    print("\n6. EFFORT (top-tier main thread)")
    eff = collections.defaultdict(lambda: [0, 0, 0.0])
    for e in L:
        if e['sub'] or not any(t in e['model'] for t in TOP_TIER): continue
        x = eff[e['effort']]; x[0] += 1; x[1] += ((e['usage'].get('output_tokens_details') or {}).get('thinking_tokens') or 0); x[2] += e['cost']
    for k, x in sorted(eff.items(), key=lambda kv: -kv[1][0]):
        print(f"   {k:<9} {x[0]:>7} req   {x[1]/x[0]:>5.0f} thinking tok/req   {money(x[2])}")
    print("\n7. BY WEEK")
    top5 = [m for m, _ in sorted(by.items(), key=lambda kv: -(kv[1]['main'] + kv[1]['sub']))[:5]]
    wk = collections.defaultdict(collections.Counter)
    for e in L:
        if not e['day']: continue
        d = dt.date.fromisoformat(e['day']); wk[(d - dt.timedelta(days=d.weekday())).isoformat()][short(e['model'])] += e['cost']
    print(f"   {'week of':<12}" + ''.join(f"{m:>12}" for m in top5) + f"{'total':>10}")
    for w in sorted(wk):
        if sum(wk[w].values()) < 20: continue
        print(f"   {w:<12}" + ''.join(f"{money(wk[w][m]):>12}" for m in top5) + f"{money(sum(wk[w].values())):>10}")
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=0)
    a = ap.parse_args()
    report(*collect(a.days), a.days)
