"""CTM001 (INCOND sin productor), CTM008 (OUTCOND sin consumidor), CTM013 (borrados) y CTM018 (auto-dependencia)."""
from __future__ import annotations

import difflib
import re
from collections import defaultdict

from ..model import OdateKind, Severity
from .base import AuditContext, rule
from .naming import job_names_index, parse_condition_name


def _suggestions(ctx: AuditContext, cond: str, consumer: str) -> list[str]:
    """Condiciones existentes que podrían ser la correcta (evidencia, no conclusión)."""
    job = ctx.job(consumer)
    out: list[str] = []
    # 1) El propio consumidor borra una condición que sí se produce y que no espera: posible renombrado.
    own_in = {c.name for c in job.in_conditions}
    for c in job.out_conditions:
        if c.is_delete and c.name not in own_in and ctx.graph.producers.get(c.name):
            out.append(c.name)
    # 2) Nombres parecidos entre las condiciones que se producen.
    cache = ctx.cache.setdefault("produced_names", sorted(ctx.graph.producers))
    for m in difflib.get_close_matches(cond, cache, n=3, cutoff=0.88):
        if m not in out:
            out.append(m)
    return out[:4]


def _manual(ctx: AuditContext, cond: str) -> bool:
    return any(re.search(p, cond) for p in ctx.config.manual_condition_patterns)


@rule("CTM001")
def incond_without_producer(ctx: AuditContext):
    findings = []
    for cond, cons in ctx.graph.consumers.items():
        if ctx.graph.producers.get(cond) or ctx.config.is_external(cond) or ctx.config.is_condition_excluded(cond, "CTM001"):
            continue
        for consumer, inc in cons:
            if ctx.excluded(consumer, "CTM001"):
                continue
            job = ctx.job(consumer)
            groups, ambiguous = job.in_condition_groups()
            group = next(g for g in groups if inc in g)
            alternatives = [c.name for c in group if c.name != cond]
            runs = ctx.ever_runs(consumer)
            sugg = _suggestions(ctx, cond, consumer)
            parsed = parse_condition_name(ctx, cond)
            named_producer = parsed[0] if parsed else None
            producer_exists = bool(named_producer and named_producer in job_names_index(ctx))
            evidence = {"odate": inc.odate, "and_or": inc.and_or, "alternativas_or": alternatives,
                        "condiciones_parecidas": sugg, "estado_planificacion": runs.value,
                        "productor_segun_nombre": named_producer, "productor_segun_nombre_existe": producer_exists}
            rec = "Verificar quién debe generar la condición. "
            if sugg:
                rec += f"Posible nombre correcto: {sugg[0]}. "
            if named_producer and not producer_exists and not sugg:
                rec += (f"El nombre indica como productor '{named_producer}', que no existe en esta malla: "
                        "probablemente es una dependencia externa no declarada. ")
            elif producer_exists:
                rec += f"El job '{named_producer}' que indica el nombre existe en la malla pero no genera esta condición. "
            rec += ("Si la genera otro sistema, declararla en external_conditions / external_condition_prefixes "
                    "de config/controlm_rules.yaml; si es manual, documentarla.")

            if alternatives and not ambiguous:
                sev, blocking = Severity.BAJA, False
                desc = (f"Espera {cond} ({inc.odate}) dentro de un grupo OR. Nadie la genera en la malla, "
                        f"pero existen alternativas: {', '.join(alternatives)}.")
            elif ambiguous:
                sev, blocking = Severity.MEDIA, False
                desc = (f"Espera {cond} ({inc.odate}), que nadie genera. La mezcla de INCOND AND/OR del job no permite "
                        "determinar con certeza si existe alternativa.")
            elif _manual(ctx, cond):
                sev, blocking = Severity.MEDIA, True
                desc = (f"Espera {cond} ({inc.odate}), que ninguna pieza de la malla genera y cuyo nombre indica "
                        "activación manual. El job no arrancará hasta que alguien añada la condición.")
            elif not runs.runs and runs.value != "UNKNOWN":
                sev, blocking = Severity.MEDIA, True
                desc = (f"Espera {cond} ({inc.odate}), que no genera ningún job de la malla y no está declarada como "
                        "externa. El job no se ordena automáticamente en el periodo analizado, por lo que el impacto "
                        "real depende de cómo se ordene.")
            else:
                sev, blocking = Severity.ALTA, True
                desc = (f"Espera {cond} ({inc.odate}). No existe ningún productor local y {cond} no está declarada "
                        "como dependencia externa ni excluida.")
            findings.append(ctx.finding(
                "CTM001", sev, f"{job.job_name} espera {cond}, que nadie genera", desc, consumer,
                condition=cond, consumers=[consumer], recommendation=rec, evidence=evidence,
                is_root_cause=blocking, root_jobs=[consumer] if blocking else [],
            ))
            if blocking:
                findings[-1].evidence["blocked_conditions"] = [cond]
    return findings


@rule("CTM008")
def outcond_without_consumer(ctx: AuditContext):
    per_job: dict[str, list] = defaultdict(list)
    for cond, prods in ctx.graph.producers.items():
        if cond in ctx.graph.consumers or ctx.config.is_condition_excluded(cond, "CTM008"):
            continue
        for p in prods:
            if not ctx.excluded(p.job, "CTM008"):
                per_job[p.job].append(p.condition)
    findings = []
    index = job_names_index(ctx)
    for key, conds in per_job.items():
        names = sorted({c.name for c in conds})
        ext = [n for n in names if ctx.config.is_external(n)]
        local = [n for n in names if n not in ext]
        # Enlace roto: el nombre apunta a un consumidor que existe en la malla y que no la espera.
        broken = []
        for n in local:
            parsed = parse_condition_name(ctx, n)
            if parsed and parsed[1] in index:
                broken.append(f"{n} → {', '.join(ctx.label(k) for k in index[parsed[1]][:2])}")
        sev = Severity.BAJA if broken else Severity.INFO
        desc = (f"Genera {len(names)} condición(es) que ningún job de esta malla consume. "
                f"{len(ext)} tienen prefijo externo (probablemente las consume otro Control-M/sistema); "
                f"{len(local)} no tienen consumidor conocido.")
        if broken:
            desc += ("\nEl nombre de estas condiciones indica un consumidor que SÍ existe en la malla pero no la "
                     "espera (posible INCOND eliminada o renombrada):\n" + "\n".join(broken[:10]))
        findings.append(ctx.finding(
            "CTM008", sev, f"{ctx.job(key).job_name}: {len(names)} OUTCOND sin consumidor", desc, key,
            condition=", ".join(names[:5]) + (" ..." if len(names) > 5 else ""), producers=[key],
            recommendation="Confirmar si el consumidor está en otra malla. Si la condición es obsoleta, eliminarla "
                           "para evitar acumulación de condiciones.",
            evidence={"sin_consumidor_locales": local, "sin_consumidor_externas": ext, "consumidor_indicado_existe": broken},
        ))
    return findings


@rule("CTM013")
def suspicious_deletions(ctx: AuditContext):
    findings = []
    for key, job in ctx.ws.jobs.items():
        if ctx.excluded(key, "CTM013"):
            continue
        own_in = {(c.name, c.odate_kind) for c in job.in_conditions}
        own_in_names = {c.name for c in job.in_conditions}
        own_add = {(c.name, c.odate_kind) for c in job.out_conditions if c.is_add}
        own_add_names = {c.name for c in job.out_conditions if c.is_add}
        others_consume, add_and_delete, odate_mismatch, unknown_cond = [], [], [], []
        for c in job.out_conditions:
            if not c.is_delete or ctx.config.is_condition_excluded(c.name, "CTM013"):
                continue
            k = (c.name, c.odate_kind)
            if k in own_add:
                add_and_delete.append(c)
            if k in own_in:
                continue
            if c.name in own_in_names:
                # Borra su INCOND pero con otra fecha: limpieza del día anterior/siguiente si es PREV/NEXT.
                if c.odate_kind not in (OdateKind.PREV, OdateKind.NEXT):
                    odate_mismatch.append(c)
                continue
            if c.name in own_add_names:
                continue   # borra su propia condición de otra fecha (rearme)
            other = [j for j in ctx.graph.consumers_of(c.name) if j != key]
            if other:
                others_consume.append((c, other))
            elif not ctx.graph.producers.get(c.name):
                unknown_cond.append(c)
        if others_consume:
            lines = [f"{c.name} ({c.odate}) — la consumen: {', '.join(ctx.label(o) for o in other[:4])}"
                     for c, other in others_consume]
            findings.append(ctx.finding(
                "CTM013", Severity.MEDIA, f"{job.job_name} borra condiciones que esperan otros jobs",
                "El job elimina (OUTCOND -) condiciones que no espera y que otros jobs consumen. Si se ejecuta antes "
                "que ellos, quedarán esperando una condición ya borrada:\n" + "\n".join(lines), key,
                condition=others_consume[0][0].name,
                consumers=sorted({o for _, other in others_consume for o in other}),
                recommendation="Comprobar que el borrado es intencionado (p.ej. reseteo de cadena) y que no puede "
                               "adelantarse al consumidor. Normalmente cada consumidor borra su propia INCOND.",
                evidence={"borrados": [c.label() for c, _ in others_consume]},
            ))
        if add_and_delete:
            findings.append(ctx.finding(
                "CTM013", Severity.MEDIA, f"{job.job_name} añade y borra la misma condición",
                "El job contiene OUTCOND '+' y '-' de la misma condición y fecha: "
                + ", ".join(c.name for c in add_and_delete) + ". El resultado depende del orden de proceso.", key,
                condition=add_and_delete[0].name, recommendation="Eliminar la entrada contradictoria.",
                evidence={"condiciones": [c.label() for c in add_and_delete]},
            ))
        if odate_mismatch:
            findings.append(ctx.finding(
                "CTM013", Severity.BAJA, f"{job.job_name} borra su INCOND con otra ODATE",
                "Borra condiciones que espera, pero con distinta fecha que la INCOND: "
                + ", ".join(c.label() for c in odate_mismatch) + ". La condición esperada puede permanecer.", key,
                condition=odate_mismatch[0].name, recommendation="Alinear la ODATE del borrado con la de la INCOND.",
            ))
        if unknown_cond:
            findings.append(ctx.finding(
                "CTM013", Severity.INFO, f"{job.job_name} borra condiciones que nadie genera ni espera",
                "Borrados de condiciones inexistentes en la malla (posibles restos de renombrados o externas): "
                + ", ".join(c.label() for c in unknown_cond[:8]), key,
                condition=unknown_cond[0].name, recommendation="Revisar si son obsoletas.",
            ))
    return findings


@rule("CTM018")
def self_dependency(ctx: AuditContext):
    findings = []
    seen = set()
    for dep in ctx.graph.self_dependencies():
        key = dep.consumer
        if (key, dep.condition) in seen or ctx.excluded(key, "CTM018"):
            continue
        seen.add((key, dep.condition))
        job = ctx.job(key)
        others = [p.job for p in ctx.graph.producers_of(dep.condition, exclude=key)]
        if not dep.same_day:
            # Espera la condición de otra fecha generada por él mismo: encadenamiento entre días.
            sev, blocking = Severity.INFO, False
            desc = (f"Espera {dep.condition} ({dep.in_odate}) que él mismo genera con ODATE {dep.out_odate}: "
                    "encadena ejecuciones de días distintos. La primera ejecución necesita que la condición exista.")
        elif others:
            sev, blocking = Severity.BAJA, False
            desc = (f"Espera {dep.condition} y también la genera él mismo. Existe otro productor "
                    f"({', '.join(ctx.label(o) for o in others[:3])}), por lo que no hay bloqueo, pero la "
                    "auto-generación no aporta nada y puede ocultar errores.")
        else:
            sev, blocking = Severity.ALTA, True
            desc = (f"Espera {dep.condition} ({dep.in_odate}) y el único productor es él mismo. Un job no puede "
                    "generar la condición que necesita para arrancar: nunca se ejecutará salvo intervención manual.")
        f = ctx.finding("CTM018", sev, f"{job.job_name} depende de sí mismo ({dep.condition})", desc, key,
                        condition=dep.condition, producers=[key] + others, consumers=[key],
                        recommendation="Eliminar la OUTCOND '+' redundante o corregir el nombre de la condición.",
                        is_root_cause=blocking, root_jobs=[key] if blocking else [])
        if blocking:
            f.evidence["blocked_conditions"] = [dep.condition]
        findings.append(f)
    return findings
