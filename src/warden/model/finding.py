"""Hallazgos de auditoría."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum


class Severity(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        return {"ALTA": 0, "MEDIA": 1, "BAJA": 2, "INFO": 3}[self.value]

    @property
    def icon(self) -> str:
        return {"ALTA": "🔴", "MEDIA": "🟠", "BAJA": "🟡", "INFO": "🔵"}[self.value]


@dataclass
class Finding:
    rule_id: str
    rule_name: str
    severity: Severity
    title: str
    description: str
    job: str | None = None              # clave FOLDER/JOBNAME#JOBISN
    job_name: str | None = None
    folder: str | None = None
    application: str | None = None
    sub_application: str | None = None
    condition: str | None = None
    producers: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    planning: str | None = None
    recommendation: str | None = None
    status: str | None = None           # p.ej. "NO VERIFICABLE DESDE ESTA MALLA"
    dates: list[str] = field(default_factory=list)
    dates_total: int = 0
    is_root_cause: bool = False
    root_cause: str | None = None
    root_jobs: list[str] = field(default_factory=list)   # jobs semilla para el cálculo de impacto
    direct_impact: list[str] = field(default_factory=list)
    indirect_impact: list[str] = field(default_factory=list)
    related_findings: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    subgraph: dict | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raw = f"{self.rule_id}|{self.job}|{self.condition}|{self.title}"
            self.id = f"{self.rule_id}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"

    @property
    def total_impact(self) -> int:
        return len(self.direct_impact) + len(self.indirect_impact)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["total_impact"] = self.total_impact
        return data
