"""The verifier-recall fixture (bead daxc) is only a fair test if every planted
defect is real. Each probe here must pass on reference.py and fail on
planted.py; a defect with no failing probe would make a verifier's "not a bug"
verdict correct rather than a dropped true positive.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from experiments.verifier_recall import build_fixture, score
from experiments.verifier_recall.defects import DEFECTS

HERE = Path(build_fixture.__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(f"vr_{name}", HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


def _funded(m, **balances):
    ledger = m.Ledger()
    for agent, amount in balances.items():
        m.deposit(ledger, agent, amount, epoch=0)
    return ledger


def probe_D01(m):
    ledger = m.Ledger()
    with pytest.raises(ValueError):
        m.deposit(ledger, "a", 0.0, 0)


def probe_D02(m):
    ledger = _funded(m, a=10.0)
    ledger.frozen.add("a")
    with pytest.raises(PermissionError):
        m.withdraw(ledger, "a", 1.0, 1)


def probe_D03(m):
    ledger = _funded(m, a=10.0)
    with pytest.raises(ValueError):
        m.withdraw(ledger, "a", 10.5, 1)


def probe_D04(m):
    ledger = _funded(m, a=1.0)
    with pytest.raises(ValueError):
        m.transfer(ledger, "a", "b", 5.0, 1)
    assert ledger.balances.get("b", 0.0) == 0.0


def probe_D05(m):
    with pytest.raises(ValueError):
        m.apply_tax(10.0, 2.0)


def probe_D06(m):
    ledger = m.Ledger()
    for epoch in range(4):
        m.deposit(ledger, "a", 1.0, epoch)
    assert [e.epoch for e in m.epoch_entries(ledger, 1, 3)] == [1, 2]


def probe_D07(m):
    ledger = m.Ledger()
    for i in range(1, 5):
        m.deposit(ledger, "a", float(i), i)
    assert m.last_n_amounts(ledger, "a", 2) == [3.0, 4.0]


def probe_D08(m):
    assert m.mean_balance(m.Ledger()) == 0.0


def probe_D09(m):
    assert m.memo_prefix(m.Entry("a", 1.0, 0), 5) == ""


def probe_D10(m):
    ledger = _funded(m, a=1.0, b=5.0, c=3.0)
    assert m.top_holders(ledger, 2) == ["b", "c"]


def probe_D11(m):
    ledger = _funded(m, a=5.0)
    assert m.freeze_if_overdrawn(ledger, limit=10.0) == []


def probe_D12(m):
    a = _funded(m, x=1.0)
    b = _funded(m, y=2.0)
    m.merge_ledgers(a, b)
    assert a.balances == {"x": 1.0}
    assert len(a.history) == 1


PROBES = {name[len("probe_"):]: fn for name, fn in globals().items() if name.startswith("probe_")}


def test_every_defect_has_a_probe():
    assert sorted(PROBES) == sorted(d.id for d in DEFECTS)


@pytest.mark.parametrize("defect_id", sorted(PROBES))
def test_probe_passes_on_reference(defect_id):
    PROBES[defect_id](_load("reference"))


@pytest.mark.parametrize("defect_id", sorted(PROBES))
def test_probe_fails_on_planted(defect_id):
    # A failed probe is a failed assert, an expected raise that did not happen
    # (pytest.fail), or the crash the defect causes. Anything else means the
    # probe is broken, not that the defect is real.
    with pytest.raises((AssertionError, pytest.fail.Exception, ZeroDivisionError, TypeError)):
        PROBES[defect_id](_load("planted"))


def test_committed_fixture_is_current():
    planted, rows = build_fixture.build()
    assert (HERE / "planted.py").read_text() == planted
    assert json.loads((HERE / "answer_key.json").read_text()) == rows


def test_answer_key_lines_point_at_the_defect():
    lines = (HERE / "planted.py").read_text().split("\n")
    for row in score.load_key():
        # The nearest def above the anchor is the function the key names.
        enclosing = next(src for src in reversed(lines[: row["line"]]) if src.startswith("def "))
        assert enclosing.startswith(f"def {row['function']}("), row["id"]


class TestScore:
    KEY = [{"id": "D1", "line": 10}, {"id": "D2", "line": 20}, {"id": "D3", "line": 30}]

    def test_matching_is_one_to_one_and_windowed(self):
        findings = [{"line": 11}, {"line": 12}, {"line": 40}]
        caught = score.match(self.KEY, findings)
        assert caught == {"D1": 0}

    def test_nearest_finding_wins(self):
        findings = [{"line": 13}, {"line": 10}]
        assert score.match(self.KEY, findings) == {"D1": 1}

    def test_dropped_rate_counts_true_findings_the_verifier_removed(self):
        review = [{"line": 10}, {"line": 20}, {"line": 99}]
        verified = [{"line": 10}]
        result = score.score(self.KEY, review, verified)
        assert result["dropped_true_positives"] == ["D2"]
        assert result["dropped_true_positive_rate"] == 0.5
        assert result["review"]["precision"] == pytest.approx(2 / 3)
        assert result["verify"]["precision"] == 1.0
        assert result["caught_only_after_verify"] == []

    def test_aggregation_rules_order_by_strictness(self):
        findings = [{"fid": "F1", "line": 10}, {"fid": "F2", "line": 20}, {"fid": "F3", "line": 30}]
        keep = {"refuted": False}
        drop = {"refuted": True}
        verdicts = [
            [dict(keep, fid="F1"), dict(keep, fid="F2"), dict(keep, fid="F3")],
            [dict(keep, fid="F1"), dict(keep, fid="F2"), dict(drop, fid="F3")],
            [dict(keep, fid="F1"), dict(drop, fid="F2")],  # F3 missing counts as refuted
        ]
        kept = {r: [f["fid"] for f in score.aggregate(findings, verdicts, r)] for r in score.RULES}
        assert kept == {"any_drop": ["F1"], "majority": ["F1", "F2"], "any_keeps": ["F1", "F2", "F3"]}
        run = score.score_run(self.KEY, findings, verdicts)
        assert run["rules"]["any_drop"]["dropped_true_positive_rate"] == pytest.approx(2 / 3)
        assert run["rules"]["any_keeps"]["dropped_true_positive_rate"] == 0.0

    def test_no_true_findings_after_review_gives_no_rate(self):
        result = score.score(self.KEY, [{"line": 99}], [])
        assert result["dropped_true_positive_rate"] is None
        assert result["verify"]["precision"] is None
