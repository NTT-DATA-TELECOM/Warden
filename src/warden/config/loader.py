"""Carga de la configuración de reglas (YAML)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "controlm_rules.yaml"


@dataclass
class AuditConfig:
    external_condition_prefixes: list[str] = field(default_factory=list)
    external_conditions: set[str] = field(default_factory=set)
    external_condition_patterns: list[re.Pattern] = field(default_factory=list)
    excluded_jobs: set[str] = field(default_factory=set)
    excluded_conditions: set[str] = field(default_factory=set)
    excluded_folders: set[str] = field(default_factory=set)
    exclusion_scope: set[str] = field(default_factory=set)
    default_days: int = 365
    week_start: int | None = None
    new_day_time: str | None = None
    user_daily_times: dict[str, str] = field(default_factory=dict)
    fan_in_info: int = 15
    fan_in_media: int = 30
    max_dates_listed: int = 15
    critical_external_impact: int = 10
    severity_overrides: dict[str, str] = field(default_factory=dict)
    disabled_rules: set[str] = field(default_factory=set)
    naming_separator: str = "-TO-"
    condition_prefix_pattern: re.Pattern = re.compile(r"^[A-Z0-9]+-")
    equivalent_job_prefixes: list[str] = field(default_factory=lambda: ["JOB_", "EXA_"])
    valid_on_codes: set[str] = field(default_factory=lambda: {"OK", "NOTOK", "*"})
    manual_condition_patterns: list[re.Pattern] = field(default_factory=list)
    source: str | None = None

    # --- Dependencias externas -------------------------------------------------
    def is_external(self, condition: str) -> bool:
        if condition in self.external_conditions:
            return True
        if any(condition.startswith(p) for p in self.external_condition_prefixes):
            return True
        return any(p.search(condition) for p in self.external_condition_patterns)

    # --- Exclusiones -----------------------------------------------------------
    def _applies(self, rule_id: str | None) -> bool:
        return not self.exclusion_scope or rule_id is None or rule_id in self.exclusion_scope

    def is_condition_excluded(self, condition: str, rule_id: str | None = None) -> bool:
        return condition in self.excluded_conditions and self._applies(rule_id)

    def is_job_excluded(self, job_name: str, folder: str, rule_id: str | None = None) -> bool:
        if not self._applies(rule_id):
            return False
        return job_name in self.excluded_jobs or f"{folder}/{job_name}" in self.excluded_jobs or folder in self.excluded_folders

    def rule_enabled(self, rule_id: str) -> bool:
        return rule_id not in self.disabled_rules


def load_config(path: str | Path | None = None) -> AuditConfig:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict = {}
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        log.info("Configuración cargada desde %s", cfg_path)
    else:
        log.warning("No se encuentra %s; se usan valores por defecto", cfg_path)

    sim = raw.get("simulation") or {}
    thr = raw.get("thresholds") or {}
    naming = raw.get("naming") or {}
    week_start = sim.get("week_start")
    return AuditConfig(
        external_condition_prefixes=[str(p) for p in raw.get("external_condition_prefixes") or []],
        external_conditions={str(c) for c in raw.get("external_conditions") or []},
        external_condition_patterns=[re.compile(str(p)) for p in raw.get("external_condition_patterns") or []],
        excluded_jobs={str(j) for j in raw.get("excluded_jobs") or []},
        excluded_conditions={str(c) for c in raw.get("excluded_conditions") or []},
        excluded_folders={str(f) for f in raw.get("excluded_folders") or []},
        exclusion_scope={str(r) for r in raw.get("exclusion_scope") or []},
        default_days=int(sim.get("default_days") or 365),
        week_start=int(week_start) if week_start is not None else None,
        new_day_time=str(sim["new_day_time"]) if sim.get("new_day_time") else None,
        user_daily_times={str(k): str(v) for k, v in (sim.get("user_daily_times") or {}).items()},
        fan_in_info=int(thr.get("fan_in_info", 15)),
        fan_in_media=int(thr.get("fan_in_media", 30)),
        max_dates_listed=int(thr.get("max_dates_listed", 15)),
        critical_external_impact=int(thr.get("critical_external_impact", 10)),
        severity_overrides={str(k): str(v).upper() for k, v in (raw.get("severity_overrides") or {}).items()},
        disabled_rules={str(r) for r in raw.get("disabled_rules") or []},
        naming_separator=str(naming.get("separator", "-TO-")),
        condition_prefix_pattern=re.compile(str(naming.get("condition_prefix_pattern", r"^[A-Z0-9]+-"))),
        equivalent_job_prefixes=[str(p) for p in naming.get("equivalent_job_prefixes", ["JOB_", "EXA_"])],
        valid_on_codes={str(c).upper() for c in raw.get("valid_on_codes") or ["OK", "NOTOK", "*"]},
        manual_condition_patterns=[re.compile(str(p)) for p in raw.get("manual_condition_patterns") or []],
        source=str(cfg_path),
    )
