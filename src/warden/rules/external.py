"""CTM009 — Dependencias externas."""
from __future__ import annotations

from ..graph import ext_node
from ..model import Severity
from .base import AuditContext, rule


@rule("CTM009")
def external_dependencies(ctx: AuditContext):
    findings = []
    for cond, cons in sorted(ctx.graph.consumers.items()):
        if not ctx.config.is_external(cond) or ctx.config.is_condition_excluded(cond, "CTM009"):
            continue
        local_prods = ctx.graph.producers.get(cond, [])
        consumers = sorted({j for j, _ in cons})
        odates = sorted({c.odate for _, c in cons})
        if local_prods:
            desc = (f"Condición con prefijo externo ({cond}) que también se genera dentro de la malla por "
                    f"{', '.join(ctx.label(p.job) for p in local_prods[:3])}. Se analiza como dependencia local.")
            findings.append(ctx.finding("CTM009", Severity.INFO, f"Condición externa {cond} con productor local", desc,
                                        consumers[0], condition=cond, producers=[p.job for p in local_prods],
                                        consumers=consumers, status="PRODUCTOR LOCAL",
                                        recommendation="Confirmar si el productor local es el esperado."))
            continue
        f = ctx.finding(
            "CTM009", Severity.INFO, f"DEPENDENCIA EXTERNA {cond}",
            f"{len(consumers)} job(s) esperan {cond} (ODATE {', '.join(odates)}), generada fuera de esta malla. "
            "No es un error, pero si la condición no llega estos jobs y todo lo que depende de ellos quedará bloqueado.",
            consumers[0], condition=cond, consumers=consumers, status="NO VERIFICABLE DESDE ESTA MALLA",
            recommendation="Monitorizar la llegada de la condición; valorar un SHOUT LATESUB o un aviso si no llega a tiempo.",
            is_root_cause=True, root_jobs=[], root_cause=ext_node(cond),
        )
        f.evidence["blocked_conditions"] = [cond]
        f.evidence["external"] = True
        findings.append(f)
    return findings
