"""Evaluación determinista de criterios de planificación de Control-M.

Cada evaluación devuelve PlanState más un motivo. Toda expresión no soportada produce UNKNOWN,
nunca FALSE: la regla fundamental es no inventar.

Semántica implementada (Control-M/Server, folders regulares):
  DAYS        ALL | n | Ln (n-ésimo día desde el final, L1 = último) | -n / -Ln (exclusión)
              Un día inexistente en el mes (31 en abril) no planifica.
  WEEKDAYS    ALL | 0..6 (0 = domingo) | -n (exclusión)
              DnWm, Dn, >n, <n, +n y similares requieren calendario/semántica no presente -> UNKNOWN.
  DAYS_AND_OR O: DAYS o WEEKDAYS. A: ambos. Si solo uno está informado se usa ese.
  Meses       JAN..DEC aplican a DAYS/WEEKDAYS.
  DATE        Lista de MMDD; independiente de los meses.
  ACTIVE_FROM / ACTIVE_TILL  fuera del periodo -> no planificado.
  DAYSCAL / WEEKSCAL / CONFCAL  sin definición de calendario en el XML -> UNKNOWN.
  SHIFT       solo es relevante con CONFCAL; con 'Ignore Job' o sin CONFCAL no altera nada.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime

from ..model import PlanState, Schedule

_TOKEN_DAY = re.compile(r"^(-)?(L)?(\d{1,2})$")
_TOKEN_WD = re.compile(r"^(-)?([0-6])$")


class _Unknown(Exception):
    pass


def _parse_day_tokens(expr: str) -> tuple[bool, list[tuple[bool, int]], list[tuple[bool, int]]]:
    """-> (all, incluidos[(es_L, n)], excluidos[(es_L, n)])"""
    expr = expr.strip().upper()
    if expr == "ALL":
        return True, [], []
    inc, exc = [], []
    for tok in expr.split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = _TOKEN_DAY.match(tok)
        if not m:
            raise _Unknown(f"DAYS='{expr}': token '{tok}' no soportado")
        neg, is_last, n = bool(m.group(1)), bool(m.group(2)), int(m.group(3))
        if n < 1 or n > 31:
            raise _Unknown(f"DAYS='{expr}': día fuera de rango '{tok}'")
        (exc if neg else inc).append((is_last, n))
    return (not inc and bool(exc)), inc, exc


def _parse_weekday_tokens(expr: str) -> tuple[bool, set[int], set[int]]:
    expr = expr.strip().upper()
    if expr == "ALL":
        return True, set(), set()
    inc, exc = set(), set()
    for tok in expr.split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = _TOKEN_WD.match(tok)
        if not m:
            raise _Unknown(f"WEEKDAYS='{expr}': token '{tok}' no soportado")
        (exc if m.group(1) else inc).add(int(m.group(2)))
    return (not inc and bool(exc)), inc, exc


def _day_matches(d: date, items: list[tuple[bool, int]]) -> bool:
    last = calendar.monthrange(d.year, d.month)[1]
    for is_last, n in items:
        target = last - n + 1 if is_last else n
        if target == d.day and 1 <= target <= last:
            return True
    return False


def _cm_weekday(d: date) -> int:
    """Control-M: 0 = domingo ... 6 = sábado."""
    return (d.weekday() + 1) % 7


def _parse_yyyymmdd(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y%m%d").date()
    except ValueError:
        return None


class CompiledSchedule:
    """Planificación precompilada para evaluar muchas fechas rápidamente."""

    def __init__(self, s: Schedule) -> None:
        self.s = s
        self.static_unknown: str | None = None
        self.days = self.weekdays = None
        self.dates: set[tuple[int, int]] = set()
        if s.uses_calendars:
            self.static_unknown = "usa calendarios (DAYSCAL/WEEKSCAL/CONFCAL) no incluidos en el XML"
            return
        try:
            if s.days:
                self.days = _parse_day_tokens(s.days)
            if s.weekdays:
                self.weekdays = _parse_weekday_tokens(s.weekdays)
            if s.date:
                for tok in s.date.split(","):
                    tok = tok.strip()
                    if len(tok) != 4 or not tok.isdigit():
                        raise _Unknown(f"DATE='{s.date}' no soportado")
                    self.dates.add((int(tok[:2]), int(tok[2:])))
        except _Unknown as exc:
            self.static_unknown = str(exc)
        self.active_from = _parse_yyyymmdd(s.active_from) if s.active_from else None
        self.active_till = _parse_yyyymmdd(s.active_till) if s.active_till else None
        if (s.active_from and not self.active_from) or (s.active_till and not self.active_till):
            self.static_unknown = self.static_unknown or "ACTIVE_FROM/ACTIVE_TILL con formato no soportado"

    def evaluate(self, d: date) -> tuple[PlanState, str]:
        s = self.s
        if self.static_unknown:
            return PlanState.UNKNOWN, self.static_unknown
        if not s.has_criteria:
            return PlanState.NOT_PLANNED, "sin criterio de planificación (no se ordena automáticamente)"
        if self.active_from and self.active_till and self.active_from > self.active_till:
            # Periodo inverso: Control-M lo interpreta como inactivo entre ambas fechas.
            if self.active_till < d < self.active_from:
                return PlanState.NOT_PLANNED, "fuera del periodo activo"
        else:
            if self.active_from and d < self.active_from:
                return PlanState.NOT_PLANNED, f"antes de ACTIVE_FROM={s.active_from}"
            if self.active_till and d > self.active_till:
                return PlanState.NOT_PLANNED, f"después de ACTIVE_TILL={s.active_till}"

        if (d.month, d.day) in self.dates:
            return PlanState.PLANNED, f"DATE={s.date}"

        if self.days is None and self.weekdays is None:
            return PlanState.NOT_PLANNED, f"DATE={s.date} no coincide"

        month_flag = s.months.get(d.month)
        if month_flag is None:
            return PlanState.UNKNOWN, "flag de mes ausente"
        if not month_flag:
            return PlanState.NOT_PLANNED, "mes no seleccionado"

        day_ok = wd_ok = None
        if self.days is not None:
            all_, inc, exc = self.days
            day_ok = (all_ or _day_matches(d, inc)) and not _day_matches(d, exc)
        if self.weekdays is not None:
            all_, inc, exc = self.weekdays
            wd = _cm_weekday(d)
            wd_ok = (all_ or wd in inc) and wd not in exc

        if day_ok is not None and wd_ok is not None:
            ok = (day_ok and wd_ok) if s.days_and_or == "A" else (day_ok or wd_ok)
        else:
            ok = day_ok if day_ok is not None else wd_ok
        return (PlanState.PLANNED, "criterios cumplidos") if ok else (PlanState.NOT_PLANNED, "criterios no cumplidos")
