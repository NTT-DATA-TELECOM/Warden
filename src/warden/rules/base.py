"""Infraestructura común de las reglas de auditoría."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from ..config import AuditConfig
from ..graph import DependencyGraph
from ..model import ControlMJob, ControlMWorkspace, Finding, PlanState, Severity
from ..scheduler import ScheduleSimulator

log = logging.getLogger(__name__)

RULES: dict[str, tuple[str, Callable[["AuditContext"], list[Finding]]]] = {}

RULE_NAMES = {
    "CTM001": "INCOND sin productor",
    "CTM002": "Productor no planificado",
    "CTM003": "Incompatibilidad ODATE",
    "CTM004": "Ciclo de dependencias",
    "CTM005": "Job imposible de ejecutar",
    "CTM006": "Bloqueo propagado",
    "CTM007": "Ventana temporal incompatible",
    "CTM008": "OUTCOND sin consumidor",
    "CTM009": "Dependencia externa",
    "CTM010": "Condición generada en resultado no OK",
    "CTM011": "Job con elevado fan-in",
    "CTM012": "Nomenclatura sospechosa",
    "CTM013": "Borrado de condición sospechoso",
    "CTM014": "Código ON no reconocido",
    "CTM015": "JOBNAME duplicado",
    "CTM016": "Planificación especial",
    "CTM017": "Planificación no verificable",
    "CTM018": "Auto-dependencia",
    "CTM020": "Incompatibilidad temporal",
}


def rule(rule_id: str):
    def deco(fn: Callable[["AuditContext"], list[Finding]]):
        RULES[rule_id] = (RULE_NAMES[rule_id], fn)
        return fn
    return deco


@dataclass
class AuditContext:
    ws: ControlMWorkspace
    config: AuditConfig
    graph: DependencyGraph
    sim: ScheduleSimulator
    cache: dict = field(default_factory=dict)

    def job(self, key: str) -> ControlMJob:
        return self.ws.jobs[key]

    def excluded(self, key: str, rule_id: str) -> bool:
        j = self.ws.jobs[key]
        return self.config.is_job_excluded(j.job_name, j.folder, rule_id)

    def planning(self, key: str) -> str:
        j = self.ws.jobs[key]
        s = self.sim.summary(key)
        sim = f"simulación {self.sim.days} días: TRUE={s['TRUE']} CONDITIONAL={s['CONDITIONAL']} UNKNOWN={s['UNKNOWN']} FALSE={s['FALSE']}"
        extra = []
        if self.graph.forced_by.get(key):
            extra.append("forzado por " + ", ".join(self.label(f) for f in self.graph.forced_by[key]))
        if key in self.sim.reasons:
            extra.append(self.sim.reasons[key])
        return " · ".join([j.schedule.describe(), sim] + extra)

    def label(self, key: str) -> str:
        j = self.ws.jobs.get(key)
        return f"{j.job_name} [{j.folder}]" if j else key

    def ever_runs(self, key: str) -> PlanState:
        """Mejor estado del job en el rango simulado."""
        best = PlanState.NOT_PLANNED
        for d in self.sim.dates:
            st = self.sim.state(key, d)
            if st == PlanState.PLANNED:
                return st
            if st == PlanState.CONDITIONAL or (st == PlanState.UNKNOWN and best == PlanState.NOT_PLANNED):
                best = st
        return best

    def fmt_dates(self, dates: list[date]) -> list[str]:
        return [d.isoformat() for d in dates[: self.config.max_dates_listed]]

    def finding(self, rule_id: str, severity: Severity, title: str, description: str, key: str | None = None,
                **kw) -> Finding:
        sev_override = self.config.severity_overrides.get(rule_id)
        if sev_override and sev_override in Severity.__members__:
            severity = Severity[sev_override]
        j = self.ws.jobs.get(key) if key else None
        if j is not None:
            kw.setdefault("planning", self.planning(key))
        return Finding(
            rule_id=rule_id, rule_name=RULE_NAMES[rule_id], severity=severity, title=title, description=description,
            job=key, job_name=j.job_name if j else kw.pop("job_name", None), folder=j.folder if j else kw.pop("folder", None),
            application=j.application if j else kw.pop("application", None),
            sub_application=j.sub_application if j else kw.pop("sub_application", None), **kw,
        )
