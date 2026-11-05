from conftest import by_rule, job, xml

from warden.model import Severity


def test_correct_dependency_is_ok(audit):
    r = audit(xml(job("A", outs=["A-TO-B"]), job("B", ins=["A-TO-B"], outs=[("A-TO-B", "ODAT", "-")])))
    assert not [f for f in r.findings if f.severity in (Severity.ALTA, Severity.MEDIA)]
    a, b = (next(k for k, j in r.workspace.jobs.items() if j.job_name == n) for n in "AB")
    assert r.graph.successors(a) == [b] and r.graph.predecessors(b) == [a]
    assert [p.job for p in r.graph.producers["A-TO-B"]] == [a]
    assert r.graph.consumers_of("A-TO-B") == [b]


def test_missing_producer_ctm001(audit):
    r = audit(xml(job("B", ins=["X"])))
    f, = by_rule(r, "CTM001")
    assert f.severity == Severity.ALTA and f.condition == "X" and f.is_root_cause


def test_dependency_not_inferred_from_name(audit):
    # El nombre A-TO-B sugiere dependencia, pero A genera otra condición: no hay arco.
    r = audit(xml(job("A", outs=["OTRA"]), job("B", ins=["A-TO-B"])))
    a = next(k for k, j in r.workspace.jobs.items() if j.job_name == "A")
    assert r.graph.successors(a) == []
    assert by_rule(r, "CTM001")


def test_or_alternative_lowers_severity(audit):
    r = audit(xml(job("A", outs=["C1"]), job("B", ins=[("C1", "ODAT", "O"), ("NADIE", "ODAT", "O")])))
    f, = by_rule(r, "CTM001")
    assert f.severity == Severity.BAJA and not f.is_root_cause


def test_condition_only_on_notok_ctm010(audit):
    notok = '<ON STMT="*" CODE="NOTOK"><DOCOND NAME="A-FAIL" ODATE="ODAT" SIGN="+"/></ON>'
    r = audit(xml(job("A", children=notok), job("B", ins=["A-FAIL"])))
    f, = by_rule(r, "CTM010")
    assert f.severity == Severity.INFO and "A-FAIL" in f.evidence["solo_en_error_con_consumidor"]
    assert not by_rule(r, "CTM001")   # el productor existe (condicional)


def test_self_dependency_without_other_producer_is_alta(audit):
    r = audit(xml(job("A", ins=["C"], outs=["C"])))
    f, = by_rule(r, "CTM018")
    assert f.severity == Severity.ALTA


def test_self_dependency_with_other_producer_is_baja(audit):
    r = audit(xml(job("P", outs=["C"]), job("A", ins=["C"], outs=["C"])))
    f, = by_rule(r, "CTM018")
    assert f.severity == Severity.BAJA


def test_delete_of_condition_consumed_by_other_ctm013(audit):
    r = audit(xml(job("P", outs=["C"]), job("X", outs=[("C", "ODAT", "-")]), job("B", ins=["C"])))
    f, = [x for x in by_rule(r, "CTM013") if x.severity == Severity.MEDIA]
    assert f.job_name == "X"


def test_not_ok_typo_ctm014(audit):
    on = '<ON STMT="*" CODE="NOT OK"><DOCOND NAME="Z" ODATE="ODAT" SIGN="+"/></ON>'
    r = audit(xml(job("A", children=on)))
    f, = by_rule(r, "CTM014")
    assert f.severity == Severity.MEDIA


def test_naming_inconsistency_ctm012(audit):
    r = audit(xml(job("A"), job("C", outs=["PFX-A-TO-B"]), job("B", ins=["PFX-A-TO-B"])))
    f, = by_rule(r, "CTM012")
    assert f.job_name == "C" and f.severity == Severity.MEDIA


def test_fan_in_ctm011(audit):
    prods = [job(f"P{i}", outs=[f"C{i}"]) for i in range(16)]
    r = audit(xml(*prods, job("B", ins=[f"C{i}" for i in range(16)])))
    f, = by_rule(r, "CTM011")
    assert f.severity == Severity.INFO
