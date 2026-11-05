"""Planificación de un job tal y como aparece en el XML (sin interpretar)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MONTH_ATTRS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


class PlanState(str, Enum):
    """Resultado de evaluar si un job está planificado una fecha.

    CONDITIONAL: el job no se ordena por calendario sino mediante DOFORCEJOB de otro job,
    por lo que solo existe si el forzador termina con el código esperado.
    """

    PLANNED = "TRUE"
    NOT_PLANNED = "FALSE"
    UNKNOWN = "UNKNOWN"
    CONDITIONAL = "CONDITIONAL"

    @property
    def runs(self) -> bool:
        return self in (PlanState.PLANNED, PlanState.CONDITIONAL)


@dataclass
class Schedule:
    days: str | None = None
    weekdays: str | None = None
    days_and_or: str = "O"
    months: dict[int, bool | None] = field(default_factory=dict)   # 1..12 -> True/False/None (ausente)
    date: str | None = None
    active_from: str | None = None
    active_till: str | None = None
    days_cal: str | None = None
    weeks_cal: str | None = None
    conf_cal: str | None = None
    shift: str | None = None
    shift_num: str | None = None
    rbc_relationship: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    max_wait: int | None = None
    max_rerun: int | None = None
    cyclic: bool = False
    interval: str | None = None
    cyclic_type: str | None = None
    cyclic_times_sequence: str | None = None
    cyclic_interval_sequence: str | None = None
    confirm: bool = False
    retro: bool = False
    timezone: str | None = None

    @property
    def has_criteria(self) -> bool:
        return bool(self.days or self.weekdays or self.date)

    @property
    def uses_calendars(self) -> bool:
        return bool(self.days_cal or self.weeks_cal or self.conf_cal)

    def months_label(self) -> str:
        flags = [self.months.get(i) for i in range(1, 13)]
        if all(f is True for f in flags):
            return "todos"
        if all(f is False for f in flags):
            return "ninguno"
        return ",".join(MONTH_ATTRS[i] for i, f in enumerate(flags) if f) or "?"

    def describe(self) -> str:
        parts: list[str] = []
        if self.days:
            parts.append(f"DAYS={self.days}")
        if self.weekdays:
            parts.append(f"WEEKDAYS={self.weekdays}")
        if self.days and self.weekdays:
            parts.append(f"DAYS_AND_OR={self.days_and_or}")
        if self.date:
            parts.append(f"DATE={self.date}")
        parts.append(f"meses={self.months_label()}")
        for label, value in (("DAYSCAL", self.days_cal), ("WEEKSCAL", self.weeks_cal), ("CONFCAL", self.conf_cal),
                             ("ACTIVE_FROM", self.active_from), ("ACTIVE_TILL", self.active_till)):
            if value:
                parts.append(f"{label}={value}")
        if self.time_from or self.time_to:
            parts.append(f"ventana={self.time_from or '----'}-{self.time_to or '----'}")
        if self.max_wait is not None:
            parts.append(f"MAXWAIT={self.max_wait}")
        if self.cyclic:
            parts.append("CÍCLICO")
        if self.confirm:
            parts.append("CONFIRM")
        if not self.has_criteria:
            parts.insert(0, "SIN CRITERIO DE PLANIFICACIÓN")
        return " | ".join(parts)
