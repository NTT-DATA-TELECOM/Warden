from conftest import ROOT, job, xml

from warden.model import ConditionRole
from warden.parser import parse_workspace

FIXTURE = ROOT / "tests" / "fixtures" / "sample_workspace.xml"


def test_parse_fixture_elements():
    ws = parse_workspace(FIXTURE)
    assert set(ws.folders) == {"FOLDER_A", "FOLDER_FORCED"}
    j = next(j for j in ws.jobs.values() if j.job_name == "JOB_B")
    assert j.job_isn == "2" and j.application == "APP" and j.sub_application == "SUB_B"
    assert j.schedule.days == "L1" and j.schedule.time_from == "0100" and j.schedule.max_wait == 3
    assert j.schedule.months[1] is True and j.schedule.months[2] is False
    assert [c.name for c in j.in_conditions] == ["A-TO-B"]
    assert {(c.name, c.sign) for c in j.out_conditions} == {("B-TO-C", "+"), ("A-TO-B", "-")}
    on = j.conditional_actions[0]
    assert on.code == "NOTOK" and on.do_conditions[0].role == ConditionRole.DO and on.do_conditions[0].conditional
    assert j.variables["%%PARM1"] == "X"
    assert j.shouts and j.shouts[0]["WHEN"] == "LATESUB"


def test_missing_attributes_are_none(tmp_path):
    p = tmp_path / "m.xml"
    p.write_text('<DEFTABLE><FOLDER FOLDER_NAME="F"><JOB JOBNAME="X"/></FOLDER></DEFTABLE>', encoding="utf-8")
    ws = parse_workspace(p)
    j = next(iter(ws.jobs.values()))
    assert j.application is None and j.schedule.days is None and j.schedule.max_wait is None
    assert j.schedule.months[1] is None
    assert not ws.folders["F"].auto_ordered


def test_duplicated_jobname_gets_unique_keys(tmp_path):
    p = tmp_path / "m.xml"
    p.write_text(xml(job("X", isn=1)) .replace("</FOLDER>", "</FOLDER>" + '<FOLDER FOLDER_NAME="F2" FOLDER_ORDER_METHOD="SYSTEM">'
                                                + job("X", isn=1) + "</FOLDER>"), encoding="utf-8")
    ws = parse_workspace(p)
    assert len(ws.jobs) == 2 and len(ws.jobs_by_name()["X"]) == 2


def test_doforcejob_parsed():
    ws = parse_workspace(FIXTURE)
    forcer = next(j for j in ws.jobs.values() if j.job_name == "FORCER")
    (action, fj), = forcer.force_jobs
    assert action.code == "OK" and fj.table == "FOLDER_FORCED" and fj.name == "*"
