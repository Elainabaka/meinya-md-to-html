"""Reports for people: Markdown (PR comments, job summaries) and one self-contained HTML page.

The HTML page is a map of the docs: one box per top-level folder, one chip
per doc, colored by health; click a chip to see its findings with evidence.
No external files, no network. Doc text only ever reaches the page through
`textContent`, never as HTML.
"""

from __future__ import annotations

import json
import posixpath
import time
from html import escape

from . import __version__

LABEL = {
    "en": {"error": "error", "warning": "warning", "info": "info", "title": "Meinya Mind Map",
           "docs": "docs", "claims": "claims checked", "verified": "verified", "time": "time",
           "nothing": "No findings at this level.", "map": "Map", "findings": "Findings",
           "filter": "filter: path, rule, text…", "allrules": "all rules",
           "red": "error", "yellow": "warning, or code changed after the doc", "green": "every claim verified",
           "gray": "nothing to check", "faded": "faded = plan or history doc", "line": "line",
           "foot": "read-only, offline",
           "unanswered": "questions git did not answer in time: findings may be missing, run again"},
    "vi": {"error": "lỗi", "warning": "cảnh báo", "info": "ghi nhận", "title": "Meinya Mind Map",
           "docs": "tài liệu", "claims": "điều kiểm được", "verified": "khớp", "time": "thời gian",
           "nothing": "Không có gì ở mức này.", "map": "Bản đồ", "findings": "Phát hiện",
           "filter": "lọc: đường dẫn, luật, chữ…", "allrules": "mọi luật",
           "red": "lỗi", "yellow": "cảnh báo, hoặc code đổi sau tài liệu", "green": "mọi điều đều khớp",
           "gray": "không có gì để kiểm", "faded": "mờ = kế hoạch hoặc lịch sử", "line": "dòng",
           "foot": "chỉ đọc, không cần mạng",
           "unanswered": "câu hỏi git không trả lời kịp: có thể thiếu phát hiện, hãy chạy lại"},
}


def _evidence(e: dict) -> str:
    parts = [e.get("rev", ""), e.get("date", "")]
    where = e.get("path", "")
    if e.get("line"):
        where += f":{e['line']}"
    parts.append(where)
    if e.get("note"):
        parts.append(e["note"])
    if e.get("text"):
        parts.append(f"\"{e['text']}\"")
    return " · ".join(p for p in parts if p)


def markdown(res, shown: list, lang: str = "en") -> str:
    L = LABEL.get(lang, LABEL["en"])
    s = res.stats
    out = [f"## {L['title']}", "",
           f"| {L['docs']} | {L['claims']} | {L['verified']} | {L['error']} | {L['warning']} | {L['info']} |",
           "|---:|---:|---:|---:|---:|---:|",
           f"| {s['docs']} | {s['checked']} | {s['verified']} | {s['error']} | {s['warning']} | {s['info']} |", ""]
    if s.get("git_unanswered"):
        out += [f"**{s['git_unanswered']} {L['unanswered']}**", ""]
    if not shown:
        out.append(L["nothing"])
        return "\n".join(out) + "\n"
    by: dict = {}
    for f in shown:
        by.setdefault(f.path, []).append(f)
    for path, items in by.items():
        out.append(f"### `{path}`")
        out.append("")
        for f in items:
            msg = f.message.replace("|", "\\|")
            out.append(f"- **{L[f.severity]}** {L['line']} {f.line} · {msg} `{f.rule}`")
            for e in f.evidence[:3]:
                out.append(f"  - {_evidence(e)}")
            if f.suggestion:
                out.append(f"  - → {f.suggestion}")
        out.append("")
    return "\n".join(out) + "\n"


def _area(path: str) -> str:
    parts = path.split("/")
    if len(parts) == 1:
        return "/"
    if len(parts) >= 3 and parts[0] in ("capabilities", "workflows", "packages", "apps", "services", "libs", "tools"):
        return "/".join(parts[:2])
    return parts[0]


def html_page(res, shown: list, lang: str = "en") -> str:
    L = LABEL.get(lang, LABEL["en"])
    docs = []
    for p, st in sorted(res.doc_stats.items()):
        docs.append({"p": p, "a": _area(p), "n": posixpath.basename(p), "t": st.get("title", ""),
                     "c": st["claims"], "ok": st["ok"], "e": st["error"], "w": st["warning"], "i": st["info"],
                     "k": st.get("type", "live"), "color": st["color"]})
    findings = [f.to_dict() for f in shown]
    # the folder name only: reports get shared, and the full path would give away the user name
    name = posixpath.basename(str(res.root).replace("\\", "/").rstrip("/")) or str(res.root)
    data = {"root": name, "stats": res.stats, "docs": docs, "findings": findings,
            "time": round(res.timings.get("total", 0), 1), "lang": lang, "labels": L,
            "generated": time.strftime("%Y-%m-%d %H:%M"), "version": __version__}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("{{TITLE}}", escape(L["title"])).replace("{{DATA}}", blob)


def html(res, shown: list, lang: str = "en") -> str:      # name used by the CLI
    return html_page(res, shown, lang)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#0d1117;--grid:rgba(255,255,255,.035);--panel:#151b23;--line:#2a313c;--ink:#e6edf3;--muted:#8b949e;
--red:#f85149;--amber:#d29922;--green:#3fb950;--gray:#6e7681;--blue:#58a6ff;--violet:#bc8cff;
--mono:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;--sans:system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:light){:root:not([data-theme="dark"]){--bg:#f6f8fa;--grid:rgba(0,0,0,.04);--panel:#fff;--line:#d0d7de;
--ink:#1f2328;--muted:#59636e;--red:#cf222e;--amber:#9a6700;--green:#1a7f37;--gray:#8c959f;--blue:#0969da;--violet:#8250df}}
:root[data-theme="light"]{--bg:#f6f8fa;--grid:rgba(0,0,0,.04);--panel:#fff;--line:#d0d7de;--ink:#1f2328;--muted:#59636e;
--red:#cf222e;--amber:#9a6700;--green:#1a7f37;--gray:#8c959f;--blue:#0969da;--violet:#8250df}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
background-size:24px 24px;color:var(--ink);font:14px/1.5 var(--sans)}
header{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid var(--line);
background:color-mix(in srgb,var(--bg) 85%,transparent);position:sticky;top:0;z-index:5;backdrop-filter:blur(8px)}
h1{font:600 16px var(--mono);margin:0;letter-spacing:.02em}
.root{color:var(--muted);font:12px var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
button,select,input{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 9px}
button{cursor:pointer}
main{max-width:1280px;margin:0 auto;padding:18px 16px 48px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:18px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.tile b{display:block;font:600 22px var(--mono)}
.tile span{color:var(--muted);font-size:12px}
.tile.error b{color:var(--red)}.tile.warning b{color:var(--amber)}.tile.ok b{color:var(--green)}
h2{font:600 13px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:22px 0 10px}
.map{display:flex;flex-wrap:wrap;gap:12px}
.area{border:1px dashed var(--line);border-radius:10px;padding:8px 10px 10px;min-width:160px;flex:1 1 220px;max-width:100%;background:color-mix(in srgb,var(--panel) 55%,transparent)}
.area h3{font:600 12px var(--mono);margin:0 0 7px;color:var(--blue);display:flex;justify-content:space-between;gap:8px}
.area h3 em{font-style:normal;color:var(--muted);font-weight:400}
.area,.chips,.f .top>*{min-width:0}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{font:11px var(--mono);padding:2px 6px;border-radius:4px;border:1px solid var(--line);cursor:pointer;max-width:100%;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:var(--panel)}
.chip.red{border-color:var(--red);color:var(--red)}.chip.yellow{border-color:var(--amber);color:var(--amber)}
.chip.green{border-color:color-mix(in srgb,var(--green) 55%,var(--line));color:var(--green)}.chip.gray{color:var(--gray)}
.chip.history,.chip.plan{opacity:.55}.chip.sel{outline:2px solid var(--violet);outline-offset:1px}
.legend{display:flex;flex-wrap:wrap;gap:14px;color:var(--muted);font-size:12px;margin:10px 0 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.bar input{flex:1 1 220px}
.bar label{display:flex;gap:4px;align-items:center;color:var(--muted);font-size:13px;white-space:nowrap}
.group{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin-bottom:10px;overflow:hidden}
.group h4{margin:0;padding:8px 12px;font:600 12.5px var(--mono);border-bottom:1px solid var(--line);word-break:break-all}
.f{padding:9px 12px;border-bottom:1px solid var(--line)}.f:last-child{border-bottom:0}
.f .top{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.pill{font:600 11px var(--mono);padding:1px 7px;border-radius:10px;text-transform:uppercase}
.pill.error{background:color-mix(in srgb,var(--red) 18%,transparent);color:var(--red)}
.pill.warning{background:color-mix(in srgb,var(--amber) 18%,transparent);color:var(--amber)}
.pill.info{background:color-mix(in srgb,var(--blue) 15%,transparent);color:var(--blue)}
.ln{font:12px var(--mono);color:var(--muted)}.rule{font:11px var(--mono);color:var(--violet)}
.msg{flex:1 1 300px;overflow-wrap:anywhere}
.ev{font:12px var(--mono);color:var(--muted);margin:4px 0 0 2px;overflow-wrap:anywhere}
.sug{overflow-wrap:anywhere}
.sug{font-size:13px;color:var(--green);margin-top:3px}
.empty{color:var(--muted);padding:16px}
footer{color:var(--muted);font-size:12px;text-align:center;padding:20px}
@media (max-width:600px){header{flex-wrap:wrap}.root{width:100%}}
</style>
</head>
<body>
<header><div style="min-width:0"><h1>◆ Meinya Mind Map</h1><div class="root" id="root"></div></div>
<button id="theme" type="button">◐</button></header>
<main>
<div class="tiles" id="tiles"></div>
<h2 id="h-map"></h2>
<div class="map" id="map"></div>
<div class="legend" id="legend"></div>
<h2 id="h-find"></h2>
<div class="bar"><input id="q" type="search">
<label><input type="checkbox" id="s-error" checked> <span id="l-error"></span></label>
<label><input type="checkbox" id="s-warning" checked> <span id="l-warning"></span></label>
<label><input type="checkbox" id="s-info"> <span id="l-info"></span></label>
<select id="rule"><option value="" id="l-all"></option></select>
<button id="clear" type="button">×</button></div>
<div id="list"></div>
</main>
<footer id="foot"></footer>
<script type="application/json" id="data">{{DATA}}</script>
<script>
(function(){
const D=JSON.parse(document.getElementById('data').textContent);const L=D.labels;
const $=id=>document.getElementById(id);
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
try{const t=localStorage.getItem('mm-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}
$('theme').onclick=()=>{const cur=document.documentElement.dataset.theme||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');
const nx=cur==='dark'?'light':'dark';document.documentElement.dataset.theme=nx;try{localStorage.setItem('mm-theme',nx)}catch(e){}};
$('root').textContent=D.root;document.documentElement.lang=D.lang;
$('h-map').textContent=L.map;$('h-find').textContent=L.findings;$('q').placeholder=L.filter;$('l-all').textContent=L.allrules;
['error','warning','info'].forEach(k=>$('l-'+k).textContent=L[k]);
const s=D.stats;const pct=s.checked?Math.floor(1000*s.verified/s.checked)/10:0;
[[s.docs,L.docs,''],[s.checked,L.claims,''],[pct+'%',L.verified,'ok'],[s.error,L.error,'error'],[s.warning,L.warning,'warning'],[s.info,L.info,''],[D.time+'s',L.time,'']]
.concat(s.git_unanswered?[[s.git_unanswered,L.unanswered,'error']]:[])
.forEach(([v,l,c])=>{const t=el('div','tile '+c);t.appendChild(el('b',null,String(v)));t.appendChild(el('span',null,l));$('tiles').appendChild(t)});
let selDoc=null;
const areas={};D.docs.forEach(d=>{(areas[d.a]=areas[d.a]||[]).push(d)});
const rank=d=>d.e*1000+d.w*10+(d.color==='yellow'?1:0);
Object.keys(areas).sort((a,b)=>areas[b].reduce((x,d)=>x+rank(d),0)-areas[a].reduce((x,d)=>x+rank(d),0)||a.localeCompare(b)).forEach(a=>{
 const box=el('div','area');const h=el('h3');h.appendChild(el('span',null,a));
 const bad=areas[a].reduce((x,d)=>x+d.e+d.w,0);h.appendChild(el('em',null,areas[a].length+' · '+bad+' ⚠'));box.appendChild(h);
 const chips=el('div','chips');
 const seen={};areas[a].forEach(d=>{seen[d.n]=(seen[d.n]||0)+1});
 const name=d=>{if(seen[d.n]<2)return d.n;const p=d.p.split('/');return p.slice(Math.max(0,p.length-2)).join('/')};
 areas[a].sort((x,y)=>rank(y)-rank(x)||x.p.localeCompare(y.p)).forEach(d=>{
  const c=el('span','chip '+d.color+' '+d.k,name(d));c.title=d.p+'\n'+d.t+'\n'+d.ok+'/'+d.c+' ok · '+d.e+' '+L.error+' · '+d.w+' '+L.warning+' · '+d.k;
  c.onclick=()=>{selDoc=selDoc===d.p?null:d.p;document.querySelectorAll('.chip.sel').forEach(x=>x.classList.remove('sel'));if(selDoc)c.classList.add('sel');render()};
  chips.appendChild(c)});
 box.appendChild(chips);$('map').appendChild(box)});
[['var(--red)',L.red],['var(--amber)',L.yellow],['var(--green)',L.green],['var(--gray)',L.gray]]
.forEach(([c,t])=>{const s=el('span');const i=el('i');i.style.background=c;s.appendChild(i);s.appendChild(document.createTextNode(t));$('legend').appendChild(s)});
$('legend').appendChild(el('span',null,L.faded));
const rules=[...new Set(D.findings.map(f=>f.rule))].sort();rules.forEach(r=>{const o=el('option',null,r);o.value=r;$('rule').appendChild(o)});
function ev(e){return [e.rev,e.date,(e.path||'')+(e.line?':'+e.line:''),e.note,e.text?'"'+e.text+'"':''].filter(Boolean).join(' · ')}
function render(){
 const q=$('q').value.toLowerCase();const r=$('rule').value;
 const sev={error:$('s-error').checked,warning:$('s-warning').checked,info:$('s-info').checked};
 const list=$('list');list.textContent='';
 const fs=D.findings.filter(f=>sev[f.severity]&&(!r||f.rule===r)&&(!selDoc||f.path===selDoc)&&
  (!q||(f.path+' '+f.message+' '+f.rule+' '+f.claim).toLowerCase().includes(q)));
 if(!fs.length){list.appendChild(el('div','empty',L.nothing));return}
 const by={};fs.forEach(f=>{(by[f.path]=by[f.path]||[]).push(f)});
 Object.keys(by).forEach(p=>{const g=el('div','group');g.appendChild(el('h4',null,p));
  by[p].forEach(f=>{const x=el('div','f');const top=el('div','top');
   top.appendChild(el('span','pill '+f.severity,L[f.severity]||f.severity));top.appendChild(el('span','ln',':'+f.line));
   top.appendChild(el('span','msg',f.message));top.appendChild(el('span','rule',f.rule));x.appendChild(top);
   (f.evidence||[]).slice(0,4).forEach(e=>x.appendChild(el('div','ev','↳ '+ev(e))));
   if(f.suggestion)x.appendChild(el('div','sug','→ '+f.suggestion));g.appendChild(x)});
  list.appendChild(g)})}
['q','rule','s-error','s-warning','s-info'].forEach(id=>$(id).addEventListener('input',render));
$('clear').onclick=()=>{$('q').value='';$('rule').value='';selDoc=null;document.querySelectorAll('.chip.sel').forEach(x=>x.classList.remove('sel'));render()};
$('foot').textContent='Meinya Mind Map '+D.version+' · '+D.generated+' · '+L.foot;
render();
})();
</script>
</body>
</html>
"""
