"""Reglas estructurales: CTM010, CTM011, CTM012, CTM014, CTM015, CTM016."""
from __future__ import annotations

import re
from collections import defaultdict

from ..model import PlanState, Severity
from .base import AuditContext, rule
from .naming import job_names_index, norm_job, parse_condition_name


@rule("CTM010")
def conditions_on_not_ok(ctx: AuditContext):
    """Condiciones que solo se generan si el job termina con un resultado distinto de OK."""
    findings = []
    for key, job in ctx.ws.jobs.items():
        if ctx.excluded(key, "CTM010"):
            continue
        conds = [c for c in job.do_conditions if c.is_add and c.conditional]
        if not conds:
            continue
        rows, critical = [], []
        for c in conds:
            consumers = [j for j in ctx.graph.consumers_of(c.name) if j != key]
            normal = [p.job for p in ctx.graph.producers_of(c.name) if not p.conditional]
            rows.append(f"{c.name} [ON {c.on_code}] -> consumidores: {len(consumers)}; productores en OK: {len(normal)}")
            if consumers and not normal:
                critical.append(c.name)
        # Solo informativo: es un diseño habitual (rama de error / continuar aunque falle).
        sev = Severity.INFO
        desc = ("El job genera condiciones mediante ON/DOCOND con un código distinto de OK. Su generación depende del "
                "resultado del job y no deben tratarse como un OUTCOND normal.\n" + "\n".join(rows))
        if critical:
            desc += ("\nLas siguientes condiciones SOLO se generan en caso de error y tienen consumidores: "
                     + ", ".join(critical) + ". Esos consumidores solo se ejecutarán cuando este job falle.")
        findings.append(ctx.finding(
            "CTM010", sev, f"{job.job_name} genera {len(conds)} condición(es) en resultado no OK", desc, key,
            condition=conds[0].name, producers=[key],
            consumers=sorted({j for c in conds for j in ctx.graph.consumers_of(c.name) if j != key}),
            recommendation="Verificar que el comportamiento ante error es el deseado (continuar la cadena, rama de aviso...).",
            evidence={"condiciones": [c.label() for c in conds], "solo_en_error_con_consumidor": critical},
        ))
    return findings


@rule("CTM011")
def high_fan_in(ctx: AuditContext):
    findings = []
    for key, job in ctx.ws.jobs.items():
        n = len(job.in_conditions)
        if n < ctx.config.fan_in_info or ctx.excluded(key, "CTM011"):
            continue
        preds = ctx.graph.predecessors(key)
        sev = Severity.MEDIA if n >= ctx.config.fan_in_media else Severity.INFO
        findings.append(ctx.finding(
            "CTM011", sev, f"{job.job_name} espera {n} condiciones",
            f"Punto sensible de la malla: espera {n} INCOND de {len(preds)} jobs predecesores. Cualquier retraso o "
            "fallo de uno de ellos retrasa este job y todo lo que cuelga de él.", key,
            producers=preds, recommendation="Revisar si todas las dependencias son necesarias o pueden agruparse.",
            evidence={"fan_in": n, "predecesores": len(preds)},
        ))
    return findings


@rule("CTM012")
def suspicious_naming(ctx: AuditContext):
    """La condición AAA-TO-BBB debería producirla AAA y consumirla BBB."""
    prefixes = ctx.config.equivalent_job_prefixes
    names = job_names_index(ctx)
    findings = []
    per_job: dict[str, list[str]] = defaultdict(list)

    for cond, cons in ctx.graph.consumers.items():
        parsed = parse_condition_name(ctx, cond)
        if not parsed or ctx.config.is_external(cond):
            continue
        src, dst = parsed
        for consumer, _ in cons:
            cj = ctx.job(consumer)
            if dst in names and norm_job(cj.job_name, prefixes) != dst and not ctx.excluded(consumer, "CTM012"):
                per_job[consumer].append(f"espera {cond}: el nombre indica consumidor {dst}")
    for cond, prods in ctx.graph.producers.items():
        parsed = parse_condition_name(ctx, cond)
        if not parsed or ctx.config.is_external(cond):
            continue
        src, dst = parsed
        for p in prods:
            pj = ctx.job(p.job)
            if src in names and norm_job(pj.job_name, prefixes) != src and not ctx.excluded(p.job, "CTM012"):
                per_job[p.job].append(f"genera {cond}: el nombre indica productor {src}")
    for key, issues in per_job.items():
        job = ctx.job(key)
        findings.append(ctx.finding(
            "CTM012", Severity.MEDIA, f"{job.job_name}: {len(issues)} condición(es) con nombre inconsistente",
            "El nombre de la condición (PRODUCTOR-TO-CONSUMIDOR) no coincide con el job que realmente la produce o "
            "consume. No es necesariamente un error (condiciones compartidas, jobs renombrados), pero dificulta el "
            "mantenimiento y suele delatar copias de jobs:\n" + "\n".join(issues[:10])
            + (f"\n... y {len(issues) - 10} más" if len(issues) > 10 else ""), key,
            recommendation="Confirmar que la dependencia es la deseada y, si es así, renombrar la condición.",
            evidence={"inconsistencias": issues},
        ))
    return findings


@rule("CTM014")
def unknown_on_codes(ctx: AuditContext):
    findings = []
    valid = ctx.config.valid_on_codes
    pat_ok = re.compile(r"^(COMPSTAT\s+(EQ|NE|GT|GE|LT|LE|EVEN|ODD)\s+(\d+|ANY|EVEN|ODD)|[><=!]+\s*\d+|SUB\d+|NOTSUB|EXERR|JNRUN|JLOST|\*.*\*)$",
                        re.IGNORECASE)
    for key, job in ctx.ws.jobs.items():
        if ctx.excluded(key, "CTM014"):
            continue
        for a in job.conditional_actions:
            code = (a.code or "").strip()
            if code.upper() in valid or pat_ok.match(code):
                continue
            hint = ""
            if re.sub(r"[\s_]", "", code.upper()) == "NOTOK":
                hint = " Probablemente se quiso escribir NOTOK; tal y como está, Control-M lo trata como texto de sysout."
            acts = [f"DOCOND {c.name} {c.sign}" for c in a.do_conditions] + [f"FORCE {f.table}/{f.name}" for f in a.force_jobs]
            acts += [f"DOACTION {x}" for x in a.do_actions] + [o["type"] for o in a.other_actions]
            sev = Severity.MEDIA if (a.do_conditions or a.force_jobs) else Severity.BAJA
            findings.append(ctx.finding(
                "CTM014", sev, f"{job.job_name}: ON CODE='{code}' no es un estado de Control-M",
                f"ON STMT='{a.stmt}' CODE='{code}' no coincide con OK/NOTOK ni con un COMPSTAT. Control-M lo compara "
                f"como texto en el sysout, por lo que las acciones ({', '.join(acts) or 'ninguna'}) pueden no "
                f"ejecutarse nunca.{hint}", key,
                condition=a.do_conditions[0].name if a.do_conditions else None,
                recommendation="Corregir el CODE (NOTOK, OK o COMPSTAT EQ n) o confirmar que es un patrón de sysout intencionado.",
                evidence={"stmt": a.stmt, "code": code, "acciones": acts},
            ))
    return findings


@rule("CTM015")
def duplicated_job_names(ctx: AuditContext):
    findings = []
    for name, keys in ctx.ws.jobs_by_name().items():
        if len(keys) < 2:
            continue
        findings.append(ctx.finding(
            "CTM015", Severity.INFO, f"JOBNAME {name} aparece {len(keys)} veces",
            "El mismo JOBNAME existe en varios jobs: " + ", ".join(keys)
            + ". Cualquier referencia por nombre (DOFORCEJOB, condiciones, operación) es ambigua.", keys[0],
            producers=keys, recommendation="Confirmar que es intencionado (p.ej. variante laborable / festivo).",
        ))
    return findings


@rule("CTM016")
def special_scheduling(ctx: AuditContext):
    """Jobs cuya planificación impide que se ordenen automáticamente en el periodo."""
    findings = []
    for key, job in ctx.ws.jobs.items():
        if ctx.excluded(key, "CTM016"):
            continue
        s = job.schedule
        reasons = []
        folder = ctx.ws.folders.get(job.folder)
        forced = ctx.graph.forced_by.get(key)
        if folder and not folder.auto_ordered:
            if not forced:
                reasons.append(f"folder {job.folder} sin FOLDER_ORDER_METHOD y ningún DOFORCEJOB lo ordena")
        elif not s.has_criteria and not forced:
            reasons.append("sin criterio de planificación (DAYS, WEEKDAYS y DATE vacíos): solo se ejecuta si se ordena manualmente")
        if s.active_till and s.active_till < ctx.sim.start.strftime("%Y%m%d"):
            reasons.append(f"ACTIVE_TILL={s.active_till} ya vencido")
        if s.has_criteria and (s.days or s.weekdays) and all(v is False for v in s.months.values()) and not s.date:
            reasons.append("todos los meses desactivados")
        if s.confirm:
            reasons.append("requiere confirmación manual (CONFIRM=1)")
        summ = ctx.sim.summary(key)
        if not reasons and s.has_criteria and summ["TRUE"] == 0 and summ["UNKNOWN"] == 0 and summ["CONDITIONAL"] == 0:
            reasons.append(f"sus criterios no coinciden con ninguna fecha del periodo simulado")
        if not reasons:
            continue
        succ = [n for n in ctx.graph.successors(key) if n in ctx.ws.jobs]
        findings.append(ctx.finding(
            "CTM016", Severity.INFO, f"{job.job_name}: no se ordena automáticamente",
            "Planificación especial: " + "; ".join(reasons) + "."
            + (f" Tiene {len(succ)} sucesor(es) directo(s); su impacto se evalúa en CTM002/CTM005." if succ else ""),
            key, recommendation="Confirmar si es un job obsoleto, de ejecución manual o pendiente de reactivar.",
            evidence={"motivos": reasons, "sucesores": len(succ)},
        ))
    return findings
