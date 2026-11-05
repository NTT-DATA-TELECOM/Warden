"""Simulador de planificación.

Calcula, para cada job y fecha lógica (ODATE), si el job se ordena:
  PLANNED      se ordena por sus criterios de planificación (folder ordenado automáticamente)
  CONDITIONAL  solo existe si otro job lo fuerza (DOFORCEJOB) y termina con el código esperado
  UNKNOWN      la información del XML no permite decidir
  NOT_PLANNED  con certeza no se ordena automáticamente

Supuestos documentados (no verificables con el XML):
  * Cada FOLDER_ORDER_METHOD (SYSTEM / User Daily) se ejecuta todos los días.
  * Todos los folders comparten la misma fecha lógica (ODATE) del datacenter.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from ..config import AuditConfig
from ..model import ControlMWorkspace, OdateKind, PlanState, odate_kind
from .calendar_rules import CompiledSchedule

log = logging.getLogger(__name__)

MARGIN_DAYS = 40          # margen antes/después del rango para resolver PREV/NEXT
PREV_SEARCH_LIMIT = 400   # días máximos de búsqueda de la fecha de planificación anterior/siguiente

_RANK = {PlanState.PLANNED: 3, PlanState.CONDITIONAL: 2, PlanState.UNKNOWN: 1, PlanState.NOT_PLANNED: 0}


def best_state(*states: PlanState) -> PlanState:
    return max(states, key=_RANK.__getitem__) if states else PlanState.NOT_PLANNED


class ScheduleSimulator:
    def __init__(self, workspace: ControlMWorkspace, config: AuditConfig, start: date, days: int) -> None:
        self.ws = workspace
        self.config = config
        self.start = start
        self.days = days
        self.end = start + timedelta(days=days - 1)
        self.ext_start = start - timedelta(days=MARGIN_DAYS)
        self.n_ext = days + 2 * MARGIN_DAYS
        self.dates = [start + timedelta(days=i) for i in range(days)]
        self._compiled: dict[str, CompiledSchedule] = {}
        self._own: dict[str, list[PlanState]] = {}
        self.states: dict[str, list[PlanState]] = {}
        self.reasons: dict[str, str] = {}
        self.forced_by: dict[str, list[tuple[str, str | None]]] = defaultdict(list)  # job -> [(forcer, on_code)]
        self._cond_date_cache: dict[tuple[str, str], tuple[dict[date, PlanState], PlanState]] = {}
        self._neighbour_cache: dict[tuple[str, date, int], date | None] = {}
        self._run()

    # ------------------------------------------------------------------ build
    def _idx(self, d: date) -> int:
        return (d - self.ext_start).days

    def in_range(self, d: date) -> bool:
        return 0 <= self._idx(d) < self.n_ext

    def _ext_dates(self):
        for i in range(self.n_ext):
            yield self.ext_start + timedelta(days=i)

    def _run(self) -> None:
        cache: dict[tuple, tuple[CompiledSchedule, list[PlanState], str]] = {}
        for key, job in self.ws.jobs.items():
            s = job.schedule
            sig = (s.days, s.weekdays, s.days_and_or, tuple(sorted(s.months.items())), s.date, s.active_from,
                   s.active_till, s.days_cal, s.weeks_cal, s.conf_cal)
            if sig not in cache:
                comp = CompiledSchedule(s)
                states, reasons = [], set()
                for d in self._ext_dates():
                    st, why = comp.evaluate(d)
                    states.append(st)
                    if st == PlanState.UNKNOWN:
                        reasons.add(why)
                cache[sig] = (comp, states, "; ".join(sorted(reasons)))
            comp, states, unk_reason = cache[sig]
            self._compiled[key] = comp
            folder = self.ws.folders.get(job.folder)
            if folder is not None and not folder.auto_ordered:
                self._own[key] = [PlanState.NOT_PLANNED] * self.n_ext
                self.reasons[key] = f"folder {job.folder} sin FOLDER_ORDER_METHOD (solo se ordena manualmente o por DOFORCEJOB)"
            else:
                self._own[key] = states
                if unk_reason:
                    self.reasons[key] = unk_reason
                elif not job.schedule.has_criteria:
                    self.reasons[key] = "sin criterio de planificación (DAYS/WEEKDAYS/DATE vacíos)"

        # Relaciones DOFORCEJOB (forzado ignora los criterios del job forzado)
        for key, job in self.ws.jobs.items():
            for action, fj in job.force_jobs:
                targets = self.ws.find_jobs(fj.table, fj.name)
                if not targets:
                    log.debug("DOFORCEJOB %s/%s desde %s sin destino en la malla", fj.table, fj.name, key)
                for t in targets:
                    self.forced_by[t].append((key, action.code))

        self.states = {k: list(v) for k, v in self._own.items()}
        # Propagación de forzados (encadenados) hasta punto fijo
        for _ in range(10):
            changed = False
            for target, forcers in self.forced_by.items():
                cur = self.states[target]
                for i in range(self.n_ext):
                    if cur[i] == PlanState.PLANNED:
                        continue
                    fs = [self.states[f][i] for f, _ in forcers if f != target]
                    if not fs:
                        continue
                    b = best_state(*fs)
                    new = PlanState.CONDITIONAL if b.runs else (PlanState.UNKNOWN if b == PlanState.UNKNOWN else None)
                    if new and _RANK[new] > _RANK[cur[i]]:
                        cur[i] = new
                        changed = True
            if not changed:
                break
        log.info("Simulación %s..%s (%d días) calculada para %d jobs", self.start, self.end, self.days, len(self.states))

    # ------------------------------------------------------------------ query
    def state(self, key: str, d: date) -> PlanState:
        i = self._idx(d)
        if 0 <= i < self.n_ext:
            return self.states[key][i]
        st, _ = self._compiled[key].evaluate(d)
        return st

    def own_state(self, key: str, d: date) -> PlanState:
        i = self._idx(d)
        if 0 <= i < self.n_ext:
            return self._own[key][i]
        st, _ = self._compiled[key].evaluate(d)
        return st

    def run_dates(self, key: str) -> list[date]:
        """Fechas del rango en las que el job se ordena (PLANNED o CONDITIONAL)."""
        return [d for d in self.dates if self.state(key, d).runs]

    def summary(self, key: str) -> dict[str, int]:
        out = {s.value: 0 for s in PlanState}
        for d in self.dates:
            out[self.state(key, d).value] += 1
        return out

    def is_forced_only(self, key: str) -> bool:
        return all(self._own[key][self._idx(d)] != PlanState.PLANNED for d in self.dates) and bool(self.forced_by.get(key))

    def _neighbour_date(self, key: str, d: date, step: int) -> date | None:
        """Fecha de planificación anterior (step=-1) o siguiente (+1) según el calendario del job.

        Para jobs sin criterio propio (forzados) Control-M usa el día natural anterior/siguiente.
        Devuelve None si no puede determinarse (UNKNOWN).
        """
        ck = (key, d, step)
        if ck in self._neighbour_cache:
            return self._neighbour_cache[ck]
        comp = self._compiled[key]
        result: date | None = None
        if comp.static_unknown:
            result = None
        elif not comp.s.has_criteria:
            result = d + timedelta(days=step)
        else:
            cur = d
            for _ in range(PREV_SEARCH_LIMIT):
                cur = cur + timedelta(days=step)
                st, _ = comp.evaluate(cur)
                if st == PlanState.PLANNED:
                    result = cur
                    break
                if st == PlanState.UNKNOWN:
                    break
        self._neighbour_cache[ck] = result
        return result

    def condition_date(self, key: str, run_date: date, odate: str) -> date | str | None:
        """Fecha de la condición referenciada por un job ordenado en run_date.

        Devuelve una fecha, 'ANY' (STAT/****/$$$$) o None (no determinable).
        """
        kind = odate_kind(odate)
        if kind == OdateKind.ODAT:
            return run_date
        if kind == OdateKind.ANY:
            return "ANY"
        if kind == OdateKind.PREV:
            return self._neighbour_date(key, run_date, -1)
        if kind == OdateKind.NEXT:
            return self._neighbour_date(key, run_date, +1)
        if kind == OdateKind.EXPLICIT:
            mm, dd = int(odate[:2]), int(odate[2:])
            try:
                return date(run_date.year, mm, dd)
            except ValueError:
                return None
        return None

    def produced_dates(self, producer: str, out_odate: str) -> tuple[dict[date, PlanState], PlanState]:
        """Fechas de condición que puede generar un productor, con el mejor estado del productor.

        Devuelve (mapa fecha->estado, estado_para_ANY_o_indeterminado).
        """
        ck = (producer, out_odate)
        if ck in self._cond_date_cache:
            return self._cond_date_cache[ck]
        result: dict[date, PlanState] = {}
        undetermined = PlanState.NOT_PLANNED
        for i, d in enumerate(self._ext_dates()):
            st = self.states[producer][i]
            if st == PlanState.NOT_PLANNED:
                continue
            cd = self.condition_date(producer, d, out_odate)
            if isinstance(cd, date):
                result[cd] = best_state(result.get(cd, PlanState.NOT_PLANNED), st)
            else:
                # ANY o no determinable: puede satisfacer cualquier fecha, sin certeza si es None
                undetermined = best_state(undetermined, st if cd == "ANY" else PlanState.UNKNOWN)
        self._cond_date_cache[ck] = (result, undetermined)
        return result, undetermined
