"""The smallest verified doc context for a task (`mindmap context "..."`).

Docs are cut at their headings; sections are ranked with BM25 against the
task, then taken best-first until the token budget is spent. Every line in
the chosen sections that the code contradicts is marked, so an agent reads
less and knows which lines not to trust. History docs rank lower than live ones.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .cost import estimate_tokens

WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)
WEIGHT = {"live": 1.0, "plan": 0.7, "history": 0.4}


def words(text: str) -> list:
    return [w.casefold() for w in WORD.findall(text)]


def sections(path: str, doc) -> list:
    """[(start_line, end_line, title)] cut at headings (level 1-3)."""
    heads = [h for h in doc.headings if h.level <= 3]
    n = len(doc.lines)
    if not heads:
        return [(1, n, path)]
    out = []
    if heads[0].line > 1:
        out.append((1, heads[0].line - 1, path))
    for i, h in enumerate(heads):
        end = heads[i + 1].line - 1 if i + 1 < len(heads) else n
        out.append((h.line, end, h.text))
    return [s for s in out if s[1] >= s[0]]


def build(root, query: str, budget: int = 2000) -> dict:
    from .doctype import classify
    from .engine import load_config, run
    from .files import Inventory
    from .mdscan import scan
    root = Path(root).resolve()
    cfg = load_config(root)
    inv = Inventory(root)
    items = []                      # (doc, start, end, title, tokens Counter, length)
    kinds = {}
    for p in inv.docs:
        d = scan(p, inv.text(p) or "")
        kinds[p] = classify(p, cfg, d.kind_mark)
        for a, b, title in sections(p, d):
            body = "\n".join(d.lines[a - 1:b])
            toks = words(p.replace("/", " ") + " " + title + " " + body)
            if toks:
                items.append((p, a, b, title, Counter(toks), len(toks), body))
    q = list(dict.fromkeys(words(query)))
    if not items or not q:
        return {"text": "", "sections": [], "tokens": 0}
    df = Counter()
    for it in items:
        df.update(set(it[4]) & set(q))
    avg = sum(it[5] for it in items) / len(items)
    n = len(items)
    scored = []
    for it in items:
        tf, length = it[4], it[5]
        s = 0.0
        for w in q:
            if not tf.get(w):
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * 2.5 / (tf[w] + 1.5 * (0.25 + 0.75 * length / avg))
        if s > 0:
            scored.append((s * WEIGHT[kinds[it[0]]], it))
    scored.sort(key=lambda x: -x[0])
    chosen, used = [], 0
    seen = set()                            # the same section in two copies of a doc is shown once
    for s, it in scored:
        key = " ".join(it[6].split())
        if key in seen:
            continue
        t = estimate_tokens(it[6])
        if used + t > budget:
            if not chosen and t > budget:       # one section larger than the budget: cut it
                chosen.append((s, it, budget))
                seen.add(key)
                used = budget
            continue
        chosen.append((s, it, t))
        seen.add(key)
        used += t
        if used >= budget * 0.95:
            break
    if not chosen:
        return {"text": "", "sections": [], "tokens": 0}
    res = run(root, focus=sorted({it[0] for _, it, _ in chosen}), light=True)
    marks: dict = {}
    for f in res.findings:
        if f.severity != "info":
            marks.setdefault((f.path, f.line), []).append(f.message)
    out, meta = [], []
    for s, (p, a, b, title, _, _, body), t in chosen:
        lines = body.split("\n")
        if t < estimate_tokens(body):
            keep, acc = [], 0
            for ln in lines:
                acc += estimate_tokens(ln) + 1
                if acc > t:
                    break
                keep.append(ln)
            lines = keep
        text_lines = []
        stale = 0
        for i, ln in enumerate(lines):
            text_lines.append(ln)
            for m in marks.get((p, a + i), []):
                text_lines.append(f"  [stale] {m}")
                stale += 1
        out.append(f"## {p}:{a}-{a + len(lines) - 1} · {title}\n" + "\n".join(text_lines))
        meta.append({"doc": p, "start": a, "end": a + len(lines) - 1, "title": title,
                     "score": round(s, 3), "tokens": t, "stale": stale})
    return {"text": "\n\n".join(out) + "\n", "sections": meta, "tokens": used}


def cli(a) -> int:
    pack = build(Path(a.root), a.query, a.budget)
    text = pack["text"] or "nothing relevant found\n"
    try:
        print(text, end="")
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode(), end="")
    print(json.dumps({"tokens": pack["tokens"], "sections": len(pack["sections"])}), flush=True)
    return 0
