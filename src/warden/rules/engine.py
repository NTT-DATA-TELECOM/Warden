"""Motor de auditoría: ejecuta las reglas registradas y consolida causa raíz / impacto."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date

from ..config import AuditConfig
from ..graph import DependencyGraph
from ..model import ControlMWorkspace, Finding
from ..scheduler import ScheduleSimulator
from .base import RULES, AuditContext
from .impact import consolidate

log = logging.getLogger(__name__)


@dataclass
class AuditResult:
    workspace: ControlMWorkspace
    config: AuditConfig
    graph: DependencyGraph
    simulator: ScheduleSimulator
    findings: list[Finding]
    timings: dict[str, float] = field(default_factory=dict)
    rule_errors: dict[str, str] = field(default_factory=dict)


class AuditEngine:
    def __init__(self, config: AuditConfig) -> None:
        self.config = config

    def run(self, ws: ControlMWorkspace, start: date, days: int, rules: list[str] | None = None) -> AuditResult:
        timings: dict[str, float] = {}
        t = time.perf_counter()
        graph = DependencyGraph(ws, self.config)
        timings["graph"] = time.perf_counter() - t
        t = time.perf_counter()
        sim = ScheduleSimulator(ws, self.config, start, days)
        timings["simulation"] = time.perf_counter() - t
        ctx = AuditContext(ws, self.config, graph, sim)

        findings: list[Finding] = []
        errors: dict[str, str] = {}
        for rid in sorted(RULES):
            if rules and rid not in rules or not self.config.rule_enabled(rid):
                continue
            name, fn = RULES[rid]
            t = time.perf_counter()
            try:
                res = fn(ctx)
            except Exception as exc:  # una regla rota no debe impedir el resto de la auditoría
                log.exception("Error en la regla %s", rid)
                errors[rid] = repr(exc)
                continue
            timings[rid] = time.perf_counter() - t
            log.info("%s %-40s %4d hallazgos (%.2fs)", rid, name, len(res), timings[rid])
            findings.extend(res)

        t = time.perf_counter()
        findings = consolidate(ctx, findings)
        timings["impact"] = time.perf_counter() - t
        findings.sort(key=lambda f: (f.severity.rank, -f.total_impact, f.rule_id, f.job or ""))
        return AuditResult(ws, self.config, graph, sim, findings, timings, errors)
