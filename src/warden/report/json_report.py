"""Informe JSON estructurado."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..model import Severity
from ..rules import RULE_NAMES, AuditResult


def build_summary(result: AuditResult) -> dict:
    ws, g = result.workspace, result.graph
    sev = Counter(f.severity.value for f in result.findings)
    ext_conds = {c for c in g.consumers if result.config.is_external(c) and not g.producers.get(c)}
    root_alta = [f for f in result.findings if f.severity == Severity.ALTA and f.is_root_cause]
    return {
        "jobs": len(ws.jobs),
        "folders": len(ws.folders),
        "dependencies": len(g.dependencies),
        "graph_edges": g.g.number_of_edges(),
        "conditions_consumed": len(g.consumers),
        "conditions_produced": len(g.producers),
        "external_dependencies": len(ext_conds),
        "isolated_jobs": len(g.isolated_jobs()),
        "severity": {s.value: sev.get(s.value, 0) for s in Severity},
        "root_causes_alta": len(root_alta),
        "by_rule": dict(sorted(Counter(f.rule_id for f in result.findings).items())),
    }


def build_payload(result: AuditResult, generated_at: datetime) -> dict:
    sim = result.simulator
    ws = result.workspace
    return {
        "tool": "Warden",
        "version": __version__,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "input_files": ws.source_files,
        "config_file": result.config.source,
        "simulation": {"start": sim.start.isoformat(), "end": sim.end.isoformat(), "days": sim.days},
        "summary": build_summary(result),
        "rules": RULE_NAMES,
        "timings_seconds": {k: round(v, 3) for k, v in result.timings.items()},
        "rule_errors": result.rule_errors,
        "parse_warnings": ws.parse_warnings,
        "folders": [
            {"name": f.name, "order_method": f.order_method, "auto_ordered": f.auto_ordered, "jobs": len(f.job_keys),
             "datacenter": f.datacenter}
            for f in ws.folders.values()
        ],
        "findings": [f.to_dict() for f in result.findings],
    }


def write_json(result: AuditResult, path: Path, generated_at: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(build_payload(result, generated_at), fh, ensure_ascii=False, indent=2, default=str)
    return path
