import pytest
from conftest import by_rule, job, xml

from warden.config import load_config
from warden.model import Severity


@pytest.mark.parametrize("prefix", ["GDW-", "1PJ1-", "GBI-"])
def test_external_prefix_is_info_never_alta(audit, prefix):
    cond = f"{prefix}X"
    r = audit(xml(job("B", ins=[cond], outs=["B-TO-C"]), job("C", ins=["B-TO-C"])))
    assert not by_rule(r, "CTM001")
    f, = by_rule(r, "CTM009")
    assert f.severity == Severity.INFO and f.status == "NO VERIFICABLE DESDE ESTA MALLA"
    assert not [x for x in r.findings if x.severity == Severity.ALTA]
    # Impacto aguas abajo calculado: B directo, C indirecto
    assert [r.workspace.jobs[k].job_name for k in f.direct_impact] == ["B"]
    assert [r.workspace.jobs[k].job_name for k in f.indirect_impact] == ["C"]
    # Forma parte del grafo
    assert f"ext:{cond}" in r.graph.g


def test_prefixes_come_from_config(audit, tmp_path):
    cfg_file = tmp_path / "rules.yaml"
    cfg_file.write_text('external_condition_prefixes: ["NEW-"]\n', encoding="utf-8")
    cfg = load_config(cfg_file)
    r = audit(xml(job("B", ins=["NEW-X"]), job("D", ins=["GDW-Y"])), config=cfg)
    assert [f.condition for f in by_rule(r, "CTM009")] == ["NEW-X"]
    assert [f.condition for f in by_rule(r, "CTM001")] == ["GDW-Y"]


def test_exclusion_differs_from_external(audit, tmp_path):
    cfg_file = tmp_path / "rules.yaml"
    cfg_file.write_text('external_condition_prefixes: []\nexcluded_conditions: ["X"]\n', encoding="utf-8")
    r = audit(xml(job("B", ins=["X"])), config=load_config(cfg_file))
    assert not by_rule(r, "CTM001") and not by_rule(r, "CTM009")


def test_critical_external(audit):
    chain = [job("J0", ins=["GDW-X"], outs=["C0"])] + [job(f"J{i}", ins=[f"C{i-1}"], outs=[f"C{i}"]) for i in range(1, 12)]
    r = audit(xml(*chain))
    f, = by_rule(r, "CTM009")
    assert f.total_impact == 12 and "CRÍTICA" in f.title
