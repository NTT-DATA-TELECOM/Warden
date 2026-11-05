"""Reglas temporales: CTM002, CTM003, CTM005, CTM007, CTM017, CTM020.

Para cada job consumidor, fecha lógica en la que se ordena y grupo AND de INCOND se calcula el
mejor estado de las alternativas: un productor satisface la condición si genera el mismo
(nombre, fecha) que espera el consumidor. Resultado por (grupo, fecha):
    PLANNED / CONDITIONAL -> satisfecho
    UNKNOWN               -> no verificable (CTM017, INFO)
    NOT_PLANNED           -> ningún productor la genera para esa fecha (ALTA si el consumidor está PLANNED)

Clasificación del fallo:
    CTM002  dependencia ODAT->ODAT y el productor no se planifica ese día
    CTM003  la ODATE de la INCOND y la de la OUTCOND no coinciden y por eso no se satisface
    CTM020  dependencias PREV/NEXT sin productor en la fecha lógica correspondiente
    CTM005  el fallo se produce en TODAS las fechas en que el consumidor se planifica
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from ..model import Condition, OdateKind, PlanState, Severity
from ..scheduler import best_state
from .base import AuditContext, rule

log = logging.getLogger(__name__)


def _producer_state(ctx: AuditContext, producer: str, out: Condition, needed: date) -> PlanState:
    sim = ctx.sim
    kind = out.odate_kind
    if kind == OdateKind.ODAT:
        return sim.state(producer, needed)
    if kind == OdateKind.ANY:
        ck = ("any_state", producer)
        if ck not in ctx.cache:
            ctx.cache[ck] = best_state(*(sim.state(producer, d) for d in sim.dates)) if sim.dates else PlanState.UNKNOWN
        return ctx.cache[ck]
    if not sim.in_range(needed):
        return PlanState.UNKNOWN
    produced, undetermined = sim.produced_dates(producer, out.odate)
    return best_state(produced.get(needed, PlanState.NOT_PLANNED), undetermined)


def _cond_state(ctx: AuditContext, consumer: str, c: Condition, needed: date) -> PlanState:
    """Mejor estado de los productores de `c` (excluido el propio consumidor) para la fecha `needed`."""
    st = PlanState.NOT_PLANNED
    for p in ctx.graph.producers_of(c.name):
        if p.job == consumer and p.condition.odate_kind == c.odate_kind:
            continue   # no puede satisfacerse a sí mismo en la misma fecha
        st = best_state(st, _producer_state(ctx, p.job, p.condition, needed))
        if st == PlanState.PLANNED:
            break
    return st


def _group_always_ok_same_day(ctx: AuditContext, key: str, group: list[Condition], run_dates) -> bool:
    """True si alguna alternativa ODAT tiene un productor ODAT PLANNED en todas las fechas de ejecución."""
    sim = ctx.sim
    for c in group:
        if c.odate_kind != OdateKind.ODAT:
            continue
        for p in ctx.graph.producers_of(c.name):
            if p.job == key or p.condition.odate_kind != OdateKind.ODAT:
                continue
            states = sim.states[p.job]
            if all(states[sim._idx(d)] == PlanState.PLANNED for d, _ in run_dates):
                return True
    return False


def _analyse(ctx: AuditContext) -> dict:
    """Resultado compartido por todas las reglas temporales (se calcula una vez)."""
    if "temporal" in ctx.cache:
        return ctx.cache["temporal"]
    sim, graph = ctx.sim, ctx.graph
    failures: dict[tuple[str, int], dict] = {}        # (consumer, group_idx) -> info
    unknown: dict[str, dict] = defaultdict(lambda: {"dates": set(), "conds": set(), "reasons": set()})
    for key, job in ctx.ws.jobs.items():
        if not job.in_conditions:
            continue
        groups, ambiguous = job.in_condition_groups()
        run_dates = [(d, sim.state(key, d)) for d in sim.dates]
        run_dates = [(d, st) for d, st in run_dates if st != PlanState.NOT_PLANNED]
        if not run_dates:
            continue
        for gi, group in enumerate(groups):
            # Solo condiciones con productor local; las huérfanas/externas las tratan CTM001/CTM009.
            if not any(graph.producers_of(c.name) for c in group):
                continue
            if any(not graph.producers_of(c.name) for c in group):
                continue   # alternativa sin productor (externa/huérfana): no se puede demostrar fallo
            if _group_always_ok_same_day(ctx, key, group, run_dates):
                continue   # vía rápida: dependencia ODAT->ODAT con productor planificado todos esos días
            for d, cst in run_dates:
                if cst == PlanState.UNKNOWN:
                    unknown[key]["dates"].add(d)
                    unknown[key]["reasons"].add(sim.reasons.get(key, "planificación del job no determinable"))
                    continue
                gstate = PlanState.NOT_PLANNED
                detail = []
                for c in group:
                    needed = sim.condition_date(key, d, c.odate)
                    if needed == "ANY":
                        cstate = best_state(*(ctx.cache.setdefault(("any_state", p.job), best_state(
                            *(sim.state(p.job, x) for x in sim.dates))) for p in graph.producers_of(c.name)))
                    elif needed is None:
                        cstate = PlanState.UNKNOWN
                        unknown[key]["reasons"].add(f"no se puede resolver ODATE {c.odate} de {c.name}")
                    else:
                        cstate = _cond_state(ctx, key, c, needed)
                    detail.append((c, needed, cstate))
                    gstate = best_state(gstate, cstate)
                    if gstate == PlanState.PLANNED:
                        break
                if gstate == PlanState.UNKNOWN:
                    unknown[key]["dates"].add(d)
                    unknown[key]["conds"].update(c.name for c, _, s in detail if s == PlanState.UNKNOWN)
                elif gstate == PlanState.NOT_PLANNED:
                    info = failures.setdefault((key, gi), {"group": group, "dates": [], "consumer_states": set(),
                                                           "needed": {}, "ambiguous": ambiguous})
                    info["dates"].append(d)
                    info["consumer_states"].add(cst)
                    for c, needed, _ in detail:
                        info["needed"].setdefault(c.name, needed)
    result = {"failures": failures, "unknown": unknown}
    ctx.cache["temporal"] = result
    return result


def _classify(ctx: AuditContext, key: str, group: list[Condition]) -> str:
    kinds = set()
    for c in group:
        for p in ctx.graph.producers_of(c.name, exclude=key):
            kinds.add((c.odate_kind, p.condition.odate_kind))
    if kinds and all(i == o == OdateKind.ODAT for i, o in kinds):
        return "CTM002"
    # La OUTCOND del productor desplaza la fecha (PREV/NEXT): la condición se genera con otra ODATE.
    if any(o in (OdateKind.PREV, OdateKind.NEXT) and i != o for i, o in kinds):
        return "CTM003"
    # INCOND PREV/NEXT: dependencia entre días cuyo productor no corre en la fecha requerida.
    return "CTM020"


def _producer_detail(ctx: AuditContext, key: str, group: list[Condition], sample: date) -> list[str]:
    lines = []
    for c in group:
        needed = ctx.sim.condition_date(key, sample, c.odate)
        for p in ctx.graph.producers_of(c.name, exclude=key):
            st = _producer_state(ctx, p.job, p.condition, needed) if isinstance(needed, date) else PlanState.UNKNOWN
            pj = ctx.job(p.job)
            lines.append(f"{c.name}: INCOND {c.odate} (necesita fecha {needed}) ← {pj.job_name} [{pj.folder}] "
                         f"OUTCOND {p.condition.odate}{' [ON ' + str(p.condition.on_code) + ']' if p.condition.on_code else ''}; "
                         f"productor {st.value} · {pj.schedule.describe()}")
    return lines


def _build_failure_findings(ctx: AuditContext) -> list:
    if "temporal_findings" in ctx.cache:
        return ctx.cache["temporal_findings"]
    data = _analyse(ctx)
    findings = []
    for (key, gi), info in sorted(data["failures"].items()):
        if ctx.excluded(key, "CTM020"):
            continue
        job = ctx.job(key)
        group, dates = info["group"], sorted(info["dates"])
        planned_dates = [d for d in ctx.sim.dates if ctx.sim.state(key, d).runs]
        always = len(dates) == len(planned_dates)
        rid = _classify(ctx, key, group)
        only_conditional = info["consumer_states"] == {PlanState.CONDITIONAL}
        conds = [c.name for c in group]
        prods = sorted({p.job for c in group for p in ctx.graph.producers_of(c.name, exclude=key)})
        detail = _producer_detail(ctx, key, group, dates[0])
        if always and not only_conditional:
            rid_final, sev = "CTM005", Severity.ALTA
            title = f"{job.job_name} nunca puede satisfacer {conds[0] if len(conds) == 1 else 'sus condiciones'}"
            desc = (f"En las {len(dates)} fechas en que el job se ordena dentro del periodo analizado, ningún productor "
                    f"genera la condición requerida ({', '.join(conds)}) para la fecha lógica correspondiente. "
                    f"Motivo de fondo: {_reason_text(rid)}.")
        else:
            rid_final = rid
            sev = Severity.MEDIA if only_conditional else Severity.ALTA
            title = f"{job.job_name}: {_short(rid)} en {len(dates)} fecha(s)"
            desc = (f"El job se ordena en {len(planned_dates)} fechas del periodo; en {len(dates)} de ellas ningún "
                    f"productor genera {', '.join(conds)} para la fecha lógica requerida. {_reason_text(rid)}.")
            if only_conditional:
                desc += " El consumidor solo existe si lo fuerza un DOFORCEJOB, por lo que el riesgo es condicional."
        if info["ambiguous"]:
            sev = Severity.MEDIA if sev == Severity.ALTA else sev
            desc += " Las INCOND mezclan AND/OR, la agrupación exacta no es verificable."
        desc += "\nDetalle (primera fecha afectada):\n" + "\n".join(detail)
        f = ctx.finding(
            rid_final, sev, title, desc, key, condition=", ".join(conds), producers=prods, consumers=[key],
            dates=ctx.fmt_dates(dates), dates_total=len(dates),
            recommendation=_recommend(rid),
            is_root_cause=sev == Severity.ALTA, root_jobs=[key] if sev == Severity.ALTA else [],
            evidence={"fechas_planificadas": len(planned_dates), "fechas_fallidas": len(dates),
                      "clasificacion": rid, "detalle": detail, "fecha_muestra": dates[0].isoformat()},
        )
        f.evidence["failing_dates_iso"] = [d.isoformat() for d in dates]
        findings.append(f)
    ctx.cache["temporal_findings"] = findings
    return findings


def _short(rid: str) -> str:
    return {"CTM002": "productor no planificado", "CTM003": "ODATE incompatible",
            "CTM020": "incompatibilidad temporal"}[rid]


def _reason_text(rid: str) -> str:
    return {
        "CTM002": "Dependencia del mismo día (ODAT→ODAT) y el productor no está planificado esas fechas",
        "CTM003": "La ODATE de la INCOND no coincide con la de la OUTCOND del productor (ODAT/PREV/NEXT), por lo que "
                  "la condición se genera con otra fecha",
        "CTM020": "La dependencia PREV/NEXT requiere un productor en otra fecha lógica en la que no está planificado",
    }[rid]


def _recommend(rid: str) -> str:
    return {
        "CTM002": "Alinear la planificación del consumidor con la del productor, o eliminar/ajustar la INCOND en las "
                  "fechas en que el productor no corre.",
        "CTM003": "Revisar la ODATE de la INCOND y de la OUTCOND: ambas deben referirse a la misma fecha lógica.",
        "CTM020": "Revisar la ODATE PREV/NEXT y el calendario del productor en la fecha lógica requerida.",
    }[rid]


@rule("CTM002")
def producer_not_planned(ctx: AuditContext):
    return [f for f in _build_failure_findings(ctx) if f.rule_id == "CTM002"]


@rule("CTM003")
def odate_incompatibility(ctx: AuditContext):
    return [f for f in _build_failure_findings(ctx) if f.rule_id == "CTM003"]


@rule("CTM020")
def temporal_incompatibility(ctx: AuditContext):
    return [f for f in _build_failure_findings(ctx) if f.rule_id == "CTM020"]


@rule("CTM005")
def impossible_job(ctx: AuditContext):
    return [f for f in _build_failure_findings(ctx) if f.rule_id == "CTM005"]


@rule("CTM017")
def unverifiable(ctx: AuditContext):
    findings = []
    data = _analyse(ctx)
    for key, info in data["unknown"].items():
        if not info["dates"] or ctx.excluded(key, "CTM017"):
            continue
        job = ctx.job(key)
        dates = sorted(info["dates"])
        reasons = sorted(r for r in info["reasons"] if r)
        findings.append(ctx.finding(
            "CTM017", Severity.INFO, f"{job.job_name}: planificación no verificable en {len(dates)} fecha(s)",
            "No verificable con la información disponible. "
            + (("Motivo: " + "; ".join(reasons) + ".") if reasons else "")
            + (f" Condiciones afectadas: {', '.join(sorted(info['conds']))}." if info["conds"] else ""), key,
            dates=ctx.fmt_dates(dates), dates_total=len(dates), status="UNKNOWN",
            recommendation="Aportar la información que falta (calendarios, inicio de semana...) en la configuración "
                           "o revisar manualmente.",
        ))
    # Jobs cuya planificación propia es UNKNOWN aunque no tengan INCOND
    for key, job in ctx.ws.jobs.items():
        if key in data["unknown"] or ctx.excluded(key, "CTM017"):
            continue
        s = ctx.sim.summary(key)
        if s["UNKNOWN"]:
            findings.append(ctx.finding(
                "CTM017", Severity.INFO, f"{job.job_name}: planificación no verificable en {s['UNKNOWN']} fecha(s)",
                "No verificable con la información disponible. Motivo: " + ctx.sim.reasons.get(key, "desconocido") + ".",
                key, dates_total=s["UNKNOWN"], status="UNKNOWN",
                recommendation="Aportar la información que falta en la configuración o revisar manualmente.",
            ))
    return findings


# ---------------------------------------------------------------------------- CTM007
def _minutes(hhmm: str | None) -> int | None:
    if not hhmm or not hhmm.isdigit() or len(hhmm) != 4:
        return None
    h, m = int(hhmm[:2]), int(hhmm[2:])
    return h * 60 + m if h < 24 and m < 60 else None


def _order_time(ctx: AuditContext, folder: str) -> int | None:
    f = ctx.ws.folders.get(folder)
    if not f or not f.order_method:
        return None
    if f.order_method.upper() == "SYSTEM":
        return _minutes(ctx.config.new_day_time)
    return _minutes(ctx.config.user_daily_times.get(f.order_method))


@rule("CTM007")
def time_window(ctx: AuditContext):
    """Ventana TIMETO del consumidor que termina antes de que el productor pueda empezar (TIMEFROM)."""
    findings = []
    for key, job in ctx.ws.jobs.items():
        ct = _minutes(job.time_to)
        if ct is None or ctx.excluded(key, "CTM007"):
            continue
        cf = _minutes(job.time_from)
        consumer_wraps = cf is not None and cf > ct
        groups, _ = job.in_condition_groups()
        for group in groups:
            # El grupo se satisface con la alternativa que antes pueda empezar.
            starts = []
            for c in group:
                for p in ctx.graph.producers_of(c.name, exclude=key):
                    if not p.condition.odate_kind == c.odate_kind == OdateKind.ODAT:
                        starts = None
                        break
                    pj = ctx.job(p.job)
                    pf = _minutes(pj.time_from)
                    starts.append((pf, p.job))
                if starts is None:
                    break
            if not starts or any(pf is None for pf, _ in starts):
                continue   # alguna alternativa sin TIMEFROM puede ejecutarse a cualquier hora
            pf, pkey = min(starts)
            pj = ctx.job(pkey)
            ot_c, ot_p = _order_time(ctx, job.folder), _order_time(ctx, pj.folder)
            if ot_c is not None and ot_p is not None:
                rel = lambda t, o: (t - o) % 1440
                pjt = _minutes(pj.time_to)
                if rel(ct, ot_c) >= rel(pf, ot_p) or consumer_wraps:
                    continue
                maxwait = job.schedule.max_wait or 0
                sev = Severity.ALTA if maxwait == 0 else Severity.MEDIA
                certainty = "imposible" if maxwait == 0 else "imposible el mismo día (se ejecutará al día siguiente por MAXWAIT)"
            else:
                if consumer_wraps or ct >= pf or _minutes(pj.time_to) is not None and _minutes(pj.time_to) < pf:
                    continue
                if (job.schedule.max_wait or 0) > 0:
                    continue   # con MAXWAIT el job puede ejecutarse en la ventana del día siguiente
                sev, certainty = Severity.MEDIA, "riesgo (las horas de ordenación de los folders no están en el XML)"
            findings.append(ctx.finding(
                "CTM007", sev, f"{job.job_name}: ventana hasta {job.time_to} antes de que {pj.job_name} empiece ({pj.time_from})",
                f"El consumidor solo puede arrancar hasta las {job.time_to} (TIMEFROM {job.time_from or '-'}), pero la "
                f"condición {', '.join(c.name for c in group)} la genera, como pronto, {pj.job_name} que no empieza "
                f"antes de las {pj.time_from}. Ejecución {certainty}. MAXWAIT del consumidor: {job.schedule.max_wait}.",
                key, condition=", ".join(c.name for c in group), producers=[p for _, p in starts], consumers=[key],
                recommendation="Ampliar el TIMETO del consumidor o adelantar el productor.",
                is_root_cause=sev == Severity.ALTA, root_jobs=[key] if sev == Severity.ALTA else [],
            ))
    return findings
