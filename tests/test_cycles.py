from conftest import by_rule, job, xml

from warden.model import Severity


def test_cycle_ctm004(audit):
    r = audit(xml(job("A", ins=["C-A"], outs=["A-B"]), job("B", ins=["A-B"], outs=["B-C"]),
                  job("C", ins=["B-C"], outs=["C-A"])))
    f, = by_rule(r, "CTM004")
    assert f.severity == Severity.ALTA
    names = {r.workspace.jobs[k].job_name for k in f.producers}
    assert names == {"A", "B", "C"}


def test_cycle_with_exit_is_baja(audit):
    r = audit(xml(job("EXT", outs=["C-A"]), job("A", ins=["C-A"], outs=["A-B"]),
                  job("B", ins=["A-B"], outs=["B-C"]), job("C", ins=["B-C"], outs=["C-A"])))
    f, = by_rule(r, "CTM004")
    assert f.severity == Severity.BAJA


def test_prev_edge_does_not_form_cycle(audit):
    # B espera la condición de A del día anterior: encadena días, no es un interbloqueo.
    r = audit(xml(job("A", ins=["B-A"], outs=["A-B"]), job("B", ins=[("A-B", "PREV")], outs=["B-A"])))
    assert not by_rule(r, "CTM004")
