"""Informe HTML autocontenido (sin dependencias externas: funciona sin conexión)."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from ..rules import RULE_NAMES, AuditResult
from .json_report import build_summary

_LIMIT_IMPACT_LIST = 300


def _finding_view(result: AuditResult, f) -> dict:
    jobs = result.workspace.jobs
    label = lambda k: f"{jobs[k].job_name} [{jobs[k].folder}]" if k in jobs else k
    return {
        "id": f.id, "rule": f.rule_id, "rule_name": f.rule_name, "sev": f.severity.value, "title": f.title,
        "desc": f.description, "job": f.job_name, "job_key": f.job, "folder": f.folder, "app": f.application,
        "subapp": f.sub_application, "cond": f.condition, "status": f.status,
        "producers": [label(p) for p in f.producers[:50]], "consumers": [label(c) for c in f.consumers[:50]],
        "planning": f.planning, "root": f.root_cause if f.root_cause not in jobs else label(f.root_cause),
        "is_root": f.is_root_cause, "rec": f.recommendation,
        "direct": [label(x) for x in f.direct_impact[:_LIMIT_IMPACT_LIST]],
        "indirect": [label(x) for x in f.indirect_impact[:_LIMIT_IMPACT_LIST]],
        "n_direct": len(f.direct_impact), "n_indirect": len(f.indirect_impact),
        "dates": f.dates, "dates_total": f.dates_total, "related": f.related_findings,
        "graph": f.subgraph if f.subgraph and f.subgraph.get("nodes") and len(f.subgraph["nodes"]) > 1 else None,
    }


def write_html(result: AuditResult, path: Path, generated_at: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    s = build_summary(result)
    data = {
        "summary": s,
        "generated": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "files": [Path(x).name for x in result.workspace.source_files],
        "sim": {"start": result.simulator.start.isoformat(), "end": result.simulator.end.isoformat(),
                "days": result.simulator.days},
        "rules": RULE_NAMES,
        "findings": [_finding_view(result, f) for f in result.findings],
    }
    payload = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    content = _TEMPLATE.replace("__DATA__", payload).replace("__TITLE__", html.escape("controlM-tool · Control-M Mesh Audit"))
    path.write_text(content, encoding="utf-8")
    return path


_TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--muted:#5d6878;--line:#e3e6eb;--accent:#2f5bd3;
--alta:#d92d20;--media:#e8740c;--baja:#c9a100;--info:#2f6fd6;--chip:#eef1f6;}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1b2129;--ink:#e6eaf0;--muted:#9aa5b4;--line:#2b333e;
--accent:#7aa2ff;--chip:#242c37;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:24px 28px 8px}h1{margin:0;font-size:22px;letter-spacing:.04em}
.sub{color:var(--muted);font-size:13px;margin-top:4px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;padding:14px 28px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.kpi span{color:var(--muted);font-size:12px}
.kpi.alta b{color:var(--alta)}.kpi.media b{color:var(--media)}.kpi.baja b{color:var(--baja)}.kpi.info b{color:var(--info)}
.filters{display:flex;flex-wrap:wrap;gap:8px;padding:6px 28px 12px;position:sticky;top:0;background:var(--bg);z-index:5;border-bottom:1px solid var(--line)}
.filters select,.filters input{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 9px;font:inherit;min-width:140px}
.filters input{flex:1;min-width:200px}.count{align-self:center;color:var(--muted);font-size:12px}
main{padding:12px 28px 60px}
.f{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--info);border-radius:10px;margin:0 0 10px}
.f.ALTA{border-left-color:var(--alta)}.f.MEDIA{border-left-color:var(--media)}.f.BAJA{border-left-color:var(--baja)}
.f summary{list-style:none;cursor:pointer;padding:12px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.f summary::-webkit-details-marker{display:none}
.sev{font-weight:700;font-size:12px;white-space:nowrap}.rid{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--chip);padding:2px 6px;border-radius:5px}
.t{flex:1;min-width:240px;font-weight:600}.tag{font-size:11px;padding:2px 7px;border-radius:10px;background:var(--chip);color:var(--muted)}
.tag.root{background:#d92d201a;color:var(--alta);font-weight:600}.imp{font-variant-numeric:tabular-nums;font-size:12px;color:var(--muted)}
.body{padding:0 16px 16px;border-top:1px solid var(--line)}
table.kv{width:100%;border-collapse:collapse;margin-top:10px}table.kv th{width:160px;text-align:left;vertical-align:top;color:var(--muted);font-weight:500;padding:5px 8px 5px 0}
table.kv td{padding:5px 0;white-space:pre-wrap;word-break:break-word}
.list{max-height:180px;overflow:auto;font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--chip);border-radius:6px;padding:6px 8px}
.graph{margin-top:12px;border:1px solid var(--line);border-radius:8px;overflow:auto;background:var(--bg)}
.legend{display:flex;gap:14px;font-size:12px;color:var(--muted);padding:6px 10px;flex-wrap:wrap}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:4px;vertical-align:-1px}
svg text{font:11px system-ui,sans-serif;fill:var(--ink)}
.more{text-align:center;margin:16px}.more button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 18px;font:inherit;cursor:pointer}
.empty{color:var(--muted);text-align:center;padding:40px}
@media(max-width:640px){header,.kpis,.filters,main{padding-left:16px;padding-right:16px}table.kv th{width:110px}}
</style>
</head>
<body>
<header><h1>CONTROL-M MESH AUDIT</h1><div class="sub" id="sub"></div></header>
<section class="kpis" id="kpis"></section>
<section class="filters">
  <select id="fSev"><option value="">Severidad: todas</option></select>
  <select id="fRule"><option value="">Regla: todas</option></select>
  <select id="fFolder"><option value="">Folder: todos</option></select>
  <select id="fApp"><option value="">Application: todas</option></select>
  <select id="fSub"><option value="">Sub-application: todas</option></select>
  <select id="fRoot"><option value="">Todos los hallazgos</option><option value="root">Solo causas raíz</option></select>
  <input id="fJob" placeholder="Buscar job / condición / texto…">
  <span class="count" id="count"></span>
</section>
<main id="list"></main>
<div class="more" id="more" hidden><button>Mostrar más</button></div>
<script>
const D = __DATA__;
const ICON = {ALTA:"🔴",MEDIA:"🟠",BAJA:"🟡",INFO:"🔵"};
const COLORS = {root:"#d92d20",blocked:"#e8740c",affected:"#c9a100",external:"#2f6fd6",missing:"#7d3fc4",context:"#8a94a3"};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const S = D.summary;
document.getElementById("sub").textContent =
  `${D.files.join(", ")} · simulación ${D.sim.start} → ${D.sim.end} (${D.sim.days} días) · generado ${D.generated}`;
const kpis = [["Jobs analizados",S.jobs],["Folders",S.folders],["Dependencias",S.dependencies],
  ["Dependencias externas",S.external_dependencies],["🔴 Errores ALTA",S.severity.ALTA,"alta"],
  ["Causas raíz ALTA",S.root_causes_alta,"alta"],["🟠 Avisos MEDIA",S.severity.MEDIA,"media"],
  ["🟡 Avisos BAJA",S.severity.BAJA,"baja"],["🔵 INFO",S.severity.INFO,"info"]];
document.getElementById("kpis").innerHTML = kpis.map(([l,v,c]) => `<div class="kpi ${c||""}"><b>${v}</b><span>${l}</span></div>`).join("");

const F = D.findings;
function fill(id, values, fmt){const el=document.getElementById(id);
  [...new Set(values.filter(Boolean))].sort().forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=fmt?fmt(v):v;el.appendChild(o);});}
fill("fSev", ["ALTA","MEDIA","BAJA","INFO"].filter(s=>F.some(f=>f.sev===s)), v=>`${ICON[v]} ${v}`);
fill("fRule", F.map(f=>f.rule), v=>`${v} — ${D.rules[v]||""}`);
fill("fFolder", F.map(f=>f.folder)); fill("fApp", F.map(f=>f.app)); fill("fSub", F.map(f=>f.subapp));
document.getElementById("fSev").querySelectorAll("option")[0].selected = true;

const PAGE = 150; let shown = PAGE, filtered = F;
const val = id => document.getElementById(id).value;
function apply(){
  const q = val("fJob").toLowerCase();
  filtered = F.filter(f => (!val("fSev")||f.sev===val("fSev")) && (!val("fRule")||f.rule===val("fRule")) &&
    (!val("fFolder")||f.folder===val("fFolder")) && (!val("fApp")||f.app===val("fApp")) &&
    (!val("fSub")||f.subapp===val("fSub")) && (!val("fRoot")||f.is_root) &&
    (!q || [f.job,f.cond,f.title,f.desc,f.id].join(" ").toLowerCase().includes(q)));
  shown = PAGE; render();
}
function list(items, total){ if(!items.length) return "—";
  return `<div class="list">${items.map(esc).join("<br>")}${total>items.length?`<br>… y ${total-items.length} más`:""}</div>`; }
function row(k, v, raw){ return v===undefined||v===null||v===""||(Array.isArray(v)&&!v.length) ? "" :
  `<tr><th>${k}</th><td>${raw?v:esc(v)}</td></tr>`; }
function card(f){
  const imp = (f.n_direct+f.n_indirect) ? `<span class="imp">impacto ${f.n_direct}+${f.n_indirect}=${f.n_direct+f.n_indirect}</span>` : "";
  return `<details class="f ${f.sev}" data-id="${f.id}"><summary><span class="sev">${ICON[f.sev]} ${f.sev}</span>
  <span class="rid">${f.rule}</span><span class="t">${esc(f.title)}</span>${f.is_root?'<span class="tag root">CAUSA RAÍZ</span>':""}
  ${f.status?`<span class="tag">${esc(f.status)}</span>`:""}${imp}</summary><div class="body"></div></details>`;
}
function body(f){
  return `<table class="kv">${row("Regla", `${f.rule} — ${f.rule_name}`)}${row("Severidad", `${ICON[f.sev]} ${f.sev}`)}
  ${row("Job", f.job_key||f.job)}${row("Folder", f.folder)}${row("Application", [f.app,f.subapp].filter(Boolean).join(" / "))}
  ${row("Descripción", f.desc)}${row("Condición", f.cond)}${row("Estado", f.status)}
  ${row("Productor", list(f.producers, f.producers.length), true)}${row("Consumidor", list(f.consumers, f.consumers.length), true)}
  ${row("Planificación", f.planning)}
  ${row("Fechas", f.dates.length?`${f.dates.join(", ")}${f.dates_total>f.dates.length?` … (${f.dates_total} en total)`:""}`:"")}
  ${row("Causa raíz", f.root)}${row("Impacto directo", f.n_direct?`${f.n_direct} jobs`+list(f.direct,f.n_direct):"", true)}
  ${row("Impacto indirecto", f.n_indirect?`${f.n_indirect} jobs`+list(f.indirect,f.n_indirect):"", true)}
  ${row("Total", (f.n_direct+f.n_indirect)?`${f.n_direct+f.n_indirect} jobs potencialmente bloqueados`:"")}
  ${row("Relacionados", f.related.join(", "))}${row("Recomendación", f.rec)}${row("ID", f.id)}</table>
  ${f.graph?`<div class="graph"><div class="legend">${legend()}${f.graph.truncated?` · mostrando ${f.graph.nodes.length} de ${f.graph.total_nodes} nodos`:""}</div>${svg(f.graph)}</div>`:""}`;
}
function legend(){return [["root","causa raíz"],["blocked","bloqueado (directo)"],["affected","afectado (indirecto)"],
  ["external","dependencia externa"],["missing","condición inexistente"]].map(([k,l])=>`<span><i style="background:${COLORS[k]}"></i>${l}</span>`).join("");}
function svg(g){
  // Disposición por capas (orden topológico simple sobre el subgrafo).
  const ids = g.nodes.map(n=>n.id), idx = Object.fromEntries(ids.map((id,i)=>[id,i]));
  const indeg = ids.map(()=>0), out = ids.map(()=>[]);
  g.edges.forEach(e=>{ if(e.from in idx && e.to in idx && e.from!==e.to){ out[idx[e.from]].push(idx[e.to]); indeg[idx[e.to]]++; }});
  const layer = ids.map(()=>0); const q = ids.map((_,i)=>i).filter(i=>!indeg[i]); const deg=[...indeg]; const seen=new Set();
  while(q.length){const u=q.shift(); seen.add(u); out[u].forEach(v=>{layer[v]=Math.max(layer[v],layer[u]+1); if(--deg[v]===0) q.push(v);});}
  ids.forEach((_,i)=>{ if(!seen.has(i)) layer[i]=Math.max(layer[i],0); });
  const layers = {}; ids.forEach((_,i)=>(layers[layer[i]] ||= []).push(i));
  const W=190, H=46, BW=170, BH=26, pos={}; let maxRow=0;
  Object.entries(layers).forEach(([l,arr])=>{ arr.forEach((i,r)=>{ pos[i]=[20+r*W, 20+l*H*1.6]; }); maxRow=Math.max(maxRow,arr.length); });
  const width = 40+maxRow*W, height = 40+(Math.max(...layer)+1)*H*1.6;
  let s = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8z" fill="#8a94a3"/></marker></defs>`;
  g.edges.forEach(e=>{ const a=pos[idx[e.from]], b=pos[idx[e.to]]; if(!a||!b) return;
    s += `<line x1="${a[0]+BW/2}" y1="${a[1]+BH}" x2="${b[0]+BW/2}" y2="${b[1]}" stroke="#8a94a3" stroke-width="1.2" ${e.kind==="force"?'stroke-dasharray="4 3"':""} marker-end="url(#a)"><title>${esc((e.conds||[]).join(", ")||e.kind)}</title></line>`; });
  g.nodes.forEach((n,i)=>{ const [x,y]=pos[i]; const c=COLORS[n.role]||COLORS.context; const lab=n.label.length>26?n.label.slice(0,25)+"…":n.label;
    s += `<g><rect x="${x}" y="${y}" width="${BW}" height="${BH}" rx="6" fill="${c}22" stroke="${c}" stroke-width="1.5"/><text x="${x+8}" y="${y+17}">${esc(lab)}</text><title>${esc(n.id)}</title></g>`; });
  return s + "</svg>";
}
function render(){
  const el = document.getElementById("list");
  el.innerHTML = filtered.length ? filtered.slice(0, shown).map(card).join("") : '<div class="empty">Sin hallazgos para estos filtros.</div>';
  document.getElementById("count").textContent = `${filtered.length} de ${F.length} hallazgos`;
  document.getElementById("more").hidden = shown >= filtered.length;
}
const byId = Object.fromEntries(F.map(f=>[f.id,f]));
document.getElementById("list").addEventListener("toggle", e => {
  const d = e.target; if(d.open && !d.dataset.loaded){ d.querySelector(".body").innerHTML = body(byId[d.dataset.id]); d.dataset.loaded=1; }
}, true);
document.querySelector("#more button").onclick = () => { shown += PAGE; render(); };
["fSev","fRule","fFolder","fApp","fSub","fRoot"].forEach(id=>document.getElementById(id).onchange=apply);
let tm; document.getElementById("fJob").oninput = () => { clearTimeout(tm); tm=setTimeout(apply,200); };
apply();
</script>
</body>
</html>
"""
