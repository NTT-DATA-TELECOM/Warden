"""CTM006 — Propagación de bloqueos, causa raíz e impacto aguas abajo.

Para cada hallazgo marcado como causa raíz (ALTA bloqueante o dependencia externa) se calcula
qué jobs no podrían ejecutarse. Si un hallazgo raíz queda dentro del impacto de otro, se
subordina a él: se indica su causa raíz y deja de considerarse raíz independiente, evitando
cientos de alertas repetidas del mismo problema.
"""
from __future__ import annotations

import logging
from datetime import date

from ..model import Finding, PlanState, Severity
from .base import AuditContext

log = logging.getLogger(__name__)


def _alive_on(ctx: AuditContext, d: date):
    return lambda k: ctx.sim.state(k, d) != PlanState.NOT_PLANNED


def compute_impact(ctx: AuditContext, f: Finding) -> None:
    seeds = set(f.root_jobs)
    blocked_conds = set(f.evidence.get("blocked_conditions", []))
    if f.rule_id in ("CTM001", "CTM018") or f.evidence.get("external"):
        seeds_for_closure, conds = set(), blocked_conds
    else:
        seeds_for_closure, conds = seeds, set()
    failing = f.evidence.get("failing_dates_iso")
    if failing:
        # Impacto en la primera fecha fallida: solo cuentan los jobs que existen ese día.
        d = date.fromisoformat(failing[0])
        impacted = ctx.graph.blocked_closure(seeds_for_closure, conds, alive=_alive_on(ctx, d))
        f.evidence["impacto_calculado_para"] = d.isoformat()
    else:
        impacted = ctx.graph.blocked_closure(seeds_for_closure, conds)
    if seeds_for_closure:
        direct, indirect = ctx.graph.split_impact(seeds_for_closure, impacted)
    elif f.evidence.get("external"):
        consumers = {j for c in conds for j, _ in ctx.graph.consumers.get(c, [])}
        # Los consumidores de la condición externa son los afectados directos; su aguas abajo, indirectos.
        direct = sorted(consumers & impacted)
        indirect = sorted(impacted - consumers)
    else:
        # CTM001/CTM018: el propio job es la causa; el impacto son sus sucesores bloqueados.
        impacted -= seeds
        direct, indirect = ctx.graph.split_impact(seeds, impacted)
    f.direct_impact = direct
    f.indirect_impact = indirect
    if f.subgraph is None:
        extra = [f.root_cause] if f.root_cause and not f.root_cause.startswith(("job:",)) and f.root_cause not in ctx.ws.jobs else []
        roots = sorted(seeds) if seeds else []
        f.subgraph = ctx.graph.subgraph(roots, direct, indirect, extra_nodes=extra)


def consolidate(ctx: AuditContext, findings: list[Finding]) -> list[Finding]:
    roots = [f for f in findings if f.is_root_cause]
    log.info("Calculando impacto de %d causas raíz", len(roots))
    for f in roots:
        compute_impact(ctx, f)
        if not f.root_cause:
            f.root_cause = f.job

    # Subordinación: un hallazgo local cuyo job está bloqueado por otra causa raíz.
    impacted_by: dict[str, list[Finding]] = {}
    for f in roots:
        for j in f.direct_impact + f.indirect_impact:
            impacted_by.setdefault(j, []).append(f)
    for f in findings:
        if not f.job or f.evidence.get("external"):
            continue
        parents = [p for p in impacted_by.get(f.job, []) if p is not f]
        if not parents:
            continue
        parent = min(parents, key=lambda p: (p.severity.rank, -p.total_impact))
        f.related_findings.append(parent.id)
        if f.is_root_cause and f.severity == Severity.ALTA and parent.severity == Severity.ALTA:
            # El problema propio queda enmascarado por uno anterior: se mantiene pero subordinado.
            f.root_cause = f"{parent.root_cause} ({parent.id})"
            f.is_root_cause = False
            f.evidence["subordinado_a"] = parent.id

    # CTM006: resumen de bloqueo propagado por cada causa raíz ALTA con impacto.
    out = list(findings)
    for f in roots:
        if not f.is_root_cause or f.total_impact == 0 or f.severity != Severity.ALTA:
            continue
        cause = f.root_cause if f.root_cause not in ctx.ws.jobs else ctx.label(f.root_cause)
        g = ctx.finding(
            "CTM006", Severity.ALTA, f"Bloqueo propagado desde {cause}: {f.total_impact} jobs",
            f"CAUSA RAÍZ: {cause} ({f.rule_id} — {f.title}).\n"
            f"Si la causa no se corrige, quedan potencialmente bloqueados {len(f.direct_impact)} jobs directamente y "
            f"{len(f.indirect_impact)} indirectamente (total {f.total_impact}).",
            f.job, condition=f.condition, root_cause=cause, is_root_cause=False,
            direct_impact=f.direct_impact, indirect_impact=f.indirect_impact,
            related_findings=[f.id], recommendation=f"Corregir la causa raíz ({f.id}); el resto se resolverá en cascada.",
            dates=f.dates, dates_total=f.dates_total, evidence={"causa": f.id},
        )
        g.subgraph = f.subgraph
        out.append(g)

    # Externas críticas
    for f in roots:
        if f.evidence.get("external") and f.total_impact >= ctx.config.critical_external_impact:
            f.title = f"DEPENDENCIA EXTERNA CRÍTICA {f.condition}"
            f.evidence["critica"] = True
    return out
