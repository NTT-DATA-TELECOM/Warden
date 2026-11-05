"""Interfaces para la futura fase de análisis de rendimiento (NO implementada).

Diseño previsto:
  * JobRun: una ejecución histórica (job, odate, inicio, fin, estado).
  * HistoryProvider: origen de las ejecuciones (CSV, BBDD, API de Control-M...).
  * PerformanceAnalyzer: combinará el DependencyGraph con las duraciones para calcular camino crítico,
    P50/P95, cuellos de botella, esperas entre jobs, paralelismo desaprovechado y jobs que retrasan
    el fin del batch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Protocol


@dataclass(frozen=True)
class JobRun:
    job_name: str
    folder: str | None
    odate: date
    start: datetime
    end: datetime | None
    status: str                      # OK / NOTOK / ...

    @property
    def duration_seconds(self) -> float | None:
        return (self.end - self.start).total_seconds() if self.end else None


class HistoryProvider(Protocol):
    def runs(self, start: date, end: date) -> Iterable[JobRun]:
        ...


@dataclass
class JobStats:
    job_key: str
    runs: int
    p50_seconds: float | None
    p95_seconds: float | None
    max_seconds: float | None


class PerformanceAnalyzer(Protocol):
    def job_stats(self) -> dict[str, JobStats]:
        ...

    def critical_path(self, odate: date) -> list[str]:
        ...
