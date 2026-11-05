from conftest import by_rule, job, xml

from warden.model import Severity


def names(r, keys):
    return sorted(r.workspace.jobs[k].job_name for k in keys)


def test_propagation_from_impossible_root(audit):
    # A espera algo que nadie genera -> A imposible; impacto = B, C, D
    r = audit(xml(job("A", ins=["NADIE"], outs=["A-B"]), job("B", ins=["A-B"], outs=["B-C"]),
                  job("C", ins=["B-C"], outs=["C-D"]), job("D", ins=["C-D"])))
    root, = by_rule(r, "CTM001")
    assert root.is_root_cause and root.severity == Severity.ALTA
    assert names(r, root.direct_impact) == ["B"]
    assert names(r, root.indirect_impact) == ["C", "D"]
    assert root.total_impact == 3
    prop, = by_rule(r, "CTM006")
    assert prop.total_impact == 3 and "A" in prop.root_cause


def test_alternative_producer_stops_propagation(audit):
    # C espera B-C, que también genera ALT: no se bloquea aunque B sí.
    r = audit(xml(job("A", ins=["NADIE"], outs=["A-B"]), job("B", ins=["A-B"], outs=["B-C"]),
                  job("ALT", outs=["B-C"]), job("C", ins=["B-C"])))
    root, = by_rule(r, "CTM001")
    assert names(r, root.direct_impact + root.indirect_impact) == ["B"]


def test_single_root_cause_not_repeated(audit):
    # Dos causas en cadena: la segunda queda subordinada a la primera, sin duplicar CTM006.
    r = audit(xml(job("A", ins=["NADIE"], outs=["A-B"]), job("B", ins=["A-B", "NADIE2"], outs=["B-C"]),
                  job("C", ins=["B-C"])))
    roots = [f for f in r.findings if f.is_root_cause and f.severity == Severity.ALTA]
    assert [f.job_name for f in roots] == ["A"]
    sub = next(f for f in by_rule(r, "CTM001") if f.job_name == "B")
    assert sub.evidence.get("subordinado_a") == roots[0].id
    assert len(by_rule(r, "CTM006")) == 1


def test_forced_folder_blocked_when_forcer_blocked(audit):
    force = '<ON STMT="*" CODE="OK"><DOFORCEJOB TABLE_NAME="F2" NAME="*" ODATE="ODAT" REMOTE="N"/></ON>'
    content = xml(job("FORCER", ins=["NADIE"], children=force),
                  extra_folders='<FOLDER FOLDER_NAME="F2">' + job("T1", days=None, outs=["T1-T2"])
                  + job("T2", days=None, ins=["T1-T2"]) + "</FOLDER>")
    r = audit(content)
    root, = by_rule(r, "CTM001")
    assert names(r, root.direct_impact + root.indirect_impact) == ["T1", "T2"]
