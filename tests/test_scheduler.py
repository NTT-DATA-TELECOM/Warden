from datetime import date

import pytest
from conftest import by_rule, job, xml

from warden.model import PlanState, Schedule, Severity
from warden.scheduler import CompiledSchedule

ALL = {i: True for i in range(1, 13)}


def ev(d, **kw):
    kw.setdefault("months", dict(ALL))
    return CompiledSchedule(Schedule(**kw)).evaluate(d)[0]


@pytest.mark.parametrize("days,d,expected", [
    ("ALL", date(2026, 10, 5), PlanState.PLANNED),
    ("3", date(2026, 10, 3), PlanState.PLANNED),
    ("3", date(2026, 10, 4), PlanState.NOT_PLANNED),
    ("4,14", date(2026, 10, 14), PlanState.PLANNED),
    ("L1", date(2026, 10, 31), PlanState.PLANNED),
    ("L1", date(2026, 2, 28), PlanState.PLANNED),
    ("L1", date(2026, 10, 30), PlanState.NOT_PLANNED),
    ("L2", date(2026, 10, 30), PlanState.PLANNED),
    ("L1,15", date(2026, 10, 15), PlanState.PLANNED),
    ("31", date(2026, 11, 30), PlanState.NOT_PLANNED),
    ("-5", date(2026, 10, 5), PlanState.NOT_PLANNED),
    ("-5", date(2026, 10, 6), PlanState.PLANNED),
])
def test_days(days, d, expected):
    assert ev(d, days=days) == expected


def test_weekdays_and_months():
    # 2026-10-04 es domingo (0 en Control-M)
    assert ev(date(2026, 10, 4), weekdays="0") == PlanState.PLANNED
    assert ev(date(2026, 10, 5), weekdays="1,2,3,4,5") == PlanState.PLANNED
    assert ev(date(2026, 10, 4), weekdays="1,2,3,4,5") == PlanState.NOT_PLANNED
    months = {**ALL, 10: False}
    assert ev(date(2026, 10, 5), days="ALL", months=months) == PlanState.NOT_PLANNED


def test_days_and_or():
    d = date(2026, 10, 5)   # lunes, día 5
    assert ev(d, days="3", weekdays="1", days_and_or="O") == PlanState.PLANNED
    assert ev(d, days="3", weekdays="1", days_and_or="A") == PlanState.NOT_PLANNED
    assert ev(d, days="5", weekdays="1", days_and_or="A") == PlanState.PLANNED


def test_date_and_active_period():
    off = {i: False for i in range(1, 13)}
    assert ev(date(2027, 1, 6), date="0106", months=off) == PlanState.PLANNED
    assert ev(date(2027, 1, 7), date="0106", months=off) == PlanState.NOT_PLANNED
    assert ev(date(2026, 10, 1), days="ALL", active_till="20150511") == PlanState.NOT_PLANNED
    assert ev(date(2026, 10, 1), days="ALL", active_from="20180311") == PlanState.PLANNED


def test_unknown_expression_is_unknown_not_false():
    assert ev(date(2026, 10, 5), weekdays="D6W1") == PlanState.UNKNOWN
    assert ev(date(2026, 10, 5), days="ALL", days_cal="CAL_X") == PlanState.UNKNOWN
    assert ev(date(2026, 10, 5), days="+3") == PlanState.UNKNOWN


def test_unknown_never_becomes_alta(audit):
    r = audit(xml(job("P", outs=["C"], days=None, weekdays="D6W1"), job("B", ins=["C"])))
    assert not [f for f in r.findings if f.severity == Severity.ALTA]
    f, = [x for x in by_rule(r, "CTM017") if x.job_name == "B"]
    assert f.severity == Severity.INFO and "No verificable" in f.description


def test_incompatible_calendars_detected(audit):
    # Productor solo los domingos, consumidor solo los lunes, dependencia ODAT->ODAT: nunca coincide.
    r = audit(xml(job("P", outs=["C"], days=None, weekdays="0"), job("B", ins=["C"], days=None, weekdays="1")))
    f, = by_rule(r, "CTM005")
    assert f.severity == Severity.ALTA and f.dates and f.dates_total > 0
    assert date.fromisoformat(f.dates[0]).weekday() == 0   # lunes


def test_partial_incompatibility_ctm002_with_dates(audit):
    r = audit(xml(job("P", outs=["C"], days="1"), job("B", ins=["C"], days="ALL")), days=31)
    f, = by_rule(r, "CTM002")
    assert f.severity == Severity.ALTA and f.dates_total == 30 and "2026-10-02" in f.dates


def test_odate_mismatch_ctm003(audit):
    # El productor genera la condición con fecha PREV pero el consumidor la espera ODAT, y ambos diarios
    # salvo el productor que no corre los domingos -> el lunes falta la condición del lunes? No: PREV de P
    # el lunes es el sábado. El domingo nadie genera la condición del domingo.
    r = audit(xml(job("P", outs=[("C", "PREV")], days=None, weekdays="1,2,3,4,5,6"), job("B", ins=["C"])))
    f, = by_rule(r, "CTM003")
    assert f.severity == Severity.ALTA


def test_prev_dependency_satisfied(audit):
    # Diario espera la condición PREV de otro diario: OK.
    r = audit(xml(job("P", outs=["C"]), job("B", ins=[("C", "PREV")])))
    assert not [f for f in r.findings if f.rule_id in ("CTM002", "CTM003", "CTM005", "CTM020")]


def test_prev_dependency_temporal_ctm020(audit):
    # B (diario) espera C de PREV; P solo corre el día 1 -> la mayoría de días falta la condición del día anterior.
    r = audit(xml(job("P", outs=["C"], days="1"), job("B", ins=[("C", "PREV")])), days=31)
    f, = by_rule(r, "CTM020")
    assert f.severity == Severity.ALTA


def test_forced_jobs_are_conditional(audit):
    force = '<ON STMT="*" CODE="OK"><DOFORCEJOB TABLE_NAME="F2" NAME="*" ODATE="ODAT" REMOTE="N"/></ON>'
    content = xml(job("FORCER", children=force),
                  extra_folders='<FOLDER FOLDER_NAME="F2">' + job("T1", days=None) + "</FOLDER>")
    r = audit(content)
    t1 = next(k for k, j in r.workspace.jobs.items() if j.job_name == "T1")
    assert r.simulator.state(t1, date(2026, 10, 5)) == PlanState.CONDITIONAL
    assert not by_rule(r, "CTM016")
