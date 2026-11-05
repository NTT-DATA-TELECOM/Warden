"""CTM004 — Ciclos de dependencias.

Solo se consideran arcos que deben satisfacerse dentro de la misma fecha lógica (ODAT/ODAT) y
no condicionados a un resultado distinto de OK. Arcos PREV/NEXT encadenan días y no forman un
interbloqueo. Un ciclo es ALTA únicamente si ninguno de sus miembros tiene una salida: un
productor alternativo, fuera del ciclo, para la condición que le une al ciclo.
"""
from __future__ import annotations

import networkx as nx

from ..model import Severity
from .base import AuditContext, rule


def _cycle_has_exit(ctx: AuditContext, members: set[str]) -> tuple[bool, list[str]]:
    """Un miembro escapa del ciclo si ninguno de sus grupos AND depende exclusivamente del ciclo."""
    exits: list[str] = []
    has_exit = False
    for key in sorted(members):
        job = ctx.job(key)
        groups, _ = job.in_condition_groups()
        trapped = False
        for group in groups:
            prod_sets = [{p.job for p in ctx.graph.producers_of(c.name, exclude=key)} for c in group]
            if all(ps and ps <= members for ps in prod_sets):
                trapped = True
            for c, ps in zip(group, prod_sets):
                if ps & members and ps - members:
                    exits.append(f"{job.job_name}: {c.name} también la genera {ctx.label(sorted(ps - members)[0])}")
        if not trapped:
            has_exit = True
    return has_exit, exits


@rule("CTM004")
def cycles(ctx: AuditContext):
    h = ctx.graph.same_day_graph()
    findings = []
    for scc in nx.strongly_connected_components(h):
        if len(scc) < 2:
            continue
        members = set(scc)
        if all(ctx.excluded(m, "CTM004") for m in members):
            continue
        try:
            cycle = [u for u, _ in nx.find_cycle(h.subgraph(members))]
        except nx.NetworkXNoCycle:
            cycle = sorted(members)
        has_exit, exits = _cycle_has_exit(ctx, members)
        path = " -> ".join(ctx.job(k).job_name for k in cycle + cycle[:1])
        conds = []
        for u, v in zip(cycle, cycle[1:] + cycle[:1]):
            conds.extend(ctx.graph.g.edges[u, v].get("conds", []))
        if has_exit:
            sev = Severity.BAJA
            desc = (f"Ciclo de dependencias del mismo día: {path}. Al menos un miembro tiene un productor alternativo "
                    "fuera del ciclo, por lo que puede romperse, pero el orden de ejecución depende de ese productor. "
                    + ("Salidas: " + "; ".join(exits[:3]) if exits else ""))
        else:
            sev = Severity.ALTA
            desc = (f"Ciclo de dependencias imposible de resolver: {path}. Cada job espera una condición que solo "
                    "genera otro miembro del ciclo; ninguno puede arrancar.")
        first = sorted(members)[0]
        f = ctx.finding("CTM004", sev, f"Ciclo entre {len(members)} jobs", desc, first,
                        condition=", ".join(dict.fromkeys(conds)), producers=sorted(members), consumers=sorted(members),
                        recommendation="Revisar las INCOND/OUTCOND del ciclo y eliminar la dependencia inversa.",
                        is_root_cause=not has_exit, root_jobs=sorted(members) if not has_exit else [],
                        evidence={"ciclo": [ctx.label(k) for k in cycle], "tiene_salida": has_exit})
        f.subgraph = ctx.graph.subgraph(sorted(members), [], [])
        findings.append(f)
    return findings
