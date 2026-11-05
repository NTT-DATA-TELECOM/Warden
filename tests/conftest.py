"""Utilidades de test: construcción de mallas XML sintéticas."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from warden.config import load_config  # noqa: E402
from warden.parser import parse_workspace  # noqa: E402
from warden.rules import AuditEngine  # noqa: E402

ALL_MONTHS = ' '.join(f'{m}="1"' for m in "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())


def job(name: str, ins=(), outs=(), days="ALL", weekdays=None, extra="", isn=None, children="", months=ALL_MONTHS):
    """ins/outs: nombres de condición o tuplas (nombre, odate[, sign|and_or])."""
    def norm(c, default):
        return (c, "ODAT", default) if isinstance(c, str) else (c[0], c[1], c[2] if len(c) > 2 else default)
    attrs = [f'JOBNAME="{name}"', f'JOBISN="{isn or abs(hash(name)) % 10000}"', 'APPLICATION="APP"',
             'SUB_APPLICATION="SUB"', 'TASKTYPE="Job"', 'MAXWAIT="0"', months]
    if days:
        attrs.append(f'DAYS="{days}"')
    if weekdays:
        attrs.append(f'WEEKDAYS="{weekdays}"')
    body = ""
    for c in ins:
        n, o, a = norm(c, "A")
        body += f'<INCOND NAME="{n}" ODATE="{o}" AND_OR="{a}"/>'
    for c in outs:
        n, o, s = norm(c, "+")
        body += f'<OUTCOND NAME="{n}" ODATE="{o}" SIGN="{s}"/>'
    return f'<JOB {" ".join(attrs)} {extra}>{body}{children}</JOB>'


def xml(*jobs: str, folder="F1", order_method="SYSTEM", extra_folders: str = "") -> str:
    om = f' FOLDER_ORDER_METHOD="{order_method}"' if order_method else ""
    return (f'<?xml version="1.0" encoding="utf-8"?><DEFTABLE><FOLDER FOLDER_NAME="{folder}" DATACENTER="DC"{om}>'
            + "".join(jobs) + f"</FOLDER>{extra_folders}</DEFTABLE>")


@pytest.fixture
def audit(tmp_path):
    def _run(content: str, start=date(2026, 10, 1), days=60, config=None):
        p = tmp_path / "malla.xml"
        p.write_text(content, encoding="utf-8")
        ws = parse_workspace(p)
        cfg = config or load_config()
        return AuditEngine(cfg).run(ws, start, days)
    return _run


def by_rule(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]
