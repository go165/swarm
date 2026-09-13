"""Tests for the A-Evolve bridge (SWARM scenarios as BenchmarkAdapter).

No live LLM calls and no ``agent_evolve`` install required: the adapter's
structural stand-ins keep everything offline. Evaluations run the real
screening scenario headlessly (subsecond at the capped size).
"""

import json

import pytest

from swarm.bridges.aevolve import (
    AevolveBridgeConfig,
    SwarmBenchmarkAdapter,
)
from swarm.bridges.aevolve.adapter import Trajectory
from swarm.domains.aevolve import (
    AevolveEvolutionAdapter,
    CandidateOutcome,
    GateDecision,
)


@pytest.fixture
def adapter():
    return SwarmBenchmarkAdapter(AevolveBridgeConfig(n_tasks=3))


def _trajectory(task, payload) -> Trajectory:
    output = payload if isinstance(payload, str) else json.dumps(payload)
    return Trajectory(task_id=task.id, output=output)


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------
def test_get_tasks_are_seeded_scenario_cells(adapter):
    tasks = adapter.get_tasks(limit=10)
    assert [t.metadata["seed"] for t in tasks] == [1000, 1001, 1002]
    assert all(t.id.startswith("aevolve_screening-train-") for t in tasks)
    # The prompt tells the agent its lever surface.
    assert "governance.transaction_tax_rate" in tasks[0].input


def test_holdout_split_uses_disjoint_seeds(adapter):
    train = {t.metadata["seed"] for t in adapter.get_tasks("train")}
    holdout = {t.metadata["seed"] for t in adapter.get_tasks("holdout")}
    assert not train & holdout


def test_limit_caps_task_count(adapter):
    assert len(adapter.get_tasks(limit=1)) == 1


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def test_evaluate_runs_scenario_and_scores(adapter):
    task = adapter.get_tasks()[0]
    feedback = adapter.evaluate(
        task, _trajectory(task, {"governance.transaction_tax_rate": 0.1})
    )
    assert 0.0 <= feedback.score <= 1.0
    assert feedback.raw["seed"] == 1000
    assert "toxicity=" in feedback.detail


def test_evaluate_is_deterministic_per_seed(adapter):
    task = adapter.get_tasks()[0]
    payload = {"governance.audit_enabled": True}
    a = adapter.evaluate(task, _trajectory(task, payload))
    b = adapter.evaluate(task, _trajectory(task, payload))
    assert a.score == b.score
    assert a.raw["toxicity"] == b.raw["toxicity"]


def test_non_whitelisted_overrides_rejected_and_reported(adapter):
    task = adapter.get_tasks()[0]
    feedback = adapter.evaluate(
        task,
        _trajectory(task, {
            "governance.audit_enabled": True,
            "simulation.n_epochs": 1,          # harness-gaming attempt
            "agents": [],                       # ditto
        }),
    )
    assert feedback.raw["applied_overrides"] == {"governance.audit_enabled": True}
    assert set(feedback.raw["rejected_overrides"]) == {"simulation.n_epochs", "agents"}
    assert "rejected_overrides" in feedback.detail


def test_evaluate_tolerates_prose_around_json(adapter):
    task = adapter.get_tasks()[0]
    feedback = adapter.evaluate(
        task,
        _trajectory(task, 'Here is my design:\n{"governance.audit_enabled": true}\nDone.'),
    )
    assert feedback.raw["applied_overrides"] == {"governance.audit_enabled": True}


@pytest.mark.parametrize("bad", ["", "no json here", '{"unterminated": ', "[1, 2]"])
def test_unparseable_output_scores_zero_with_guidance(adapter, bad):
    task = adapter.get_tasks()[0]
    feedback = adapter.evaluate(task, _trajectory(task, bad))
    assert not feedback.success
    assert feedback.score == 0.0
    assert "REJECTED" in feedback.detail
    assert "JSON object" in feedback.detail  # actionable guidance for the evolver


def test_s_soft_score_mode_stays_in_range():
    adapter = SwarmBenchmarkAdapter(
        AevolveBridgeConfig(n_tasks=1, score_mode="s_soft")
    )
    task = adapter.get_tasks()[0]
    feedback = adapter.evaluate(task, _trajectory(task, {}))
    assert 0.0 <= feedback.score <= 1.0
    assert feedback.raw["score_mode"] == "s_soft"


def _score(adapter, payload):
    task = adapter.get_tasks()[0]
    return adapter.evaluate(task, _trajectory(task, payload))


def test_default_score_does_not_reward_shutting_the_market_down(adapter):
    # Resources start at 100 and payoffs never move them, so this stake blocks
    # every agent. Under one_minus_toxicity that scored a perfect 1.0.
    shutdown = _score(adapter, {"governance.staking_enabled": True,
                                "governance.min_stake_to_participate": 101.0})
    assert shutdown.raw["total_welfare"] == 0.0
    assert shutdown.score == 0.0
    assert not shutdown.success
    assert _score(adapter, {}).score > 0.0


def test_one_minus_toxicity_scores_zero_when_nothing_is_accepted():
    adapter = SwarmBenchmarkAdapter(AevolveBridgeConfig(n_tasks=1, score_mode="one_minus_toxicity"))
    shutdown = _score(adapter, {"governance.staking_enabled": True,
                                "governance.min_stake_to_participate": 101.0})
    assert shutdown.score == 0.0


def test_welfare_weighted_registers_welfare_moves(adapter):
    null = _score(adapter, {})
    taxed = _score(adapter, {"governance.transaction_tax_rate": 0.3})
    assert taxed.raw["total_welfare"] < null.raw["total_welfare"]
    assert taxed.score < null.score


@pytest.mark.parametrize("tuned", [
    {"governance.audit_enabled": True, "governance.audit_probability": 0.5,
     "governance.audit_threshold_p": 0.7},
    {"governance.circuit_breaker_enabled": True,
     "governance.freeze_threshold_toxicity": 0.4,
     "governance.freeze_threshold_violations": 2},
])
def test_tuned_audit_and_breaker_move_the_score(adapter, tuned):
    """Enabled at their defaults these levers never trigger at benchmark scale
    and scored exactly the null candidate (beads 2qgp, sw83). Their thresholds
    are whitelisted so a candidate can make them bind."""
    result = _score(adapter, tuned)
    assert result.raw["rejected_overrides"] == {}
    assert result.score != _score(adapter, {}).score


def test_unknown_score_mode_raises():
    adapter = SwarmBenchmarkAdapter(AevolveBridgeConfig(n_tasks=1, score_mode="nope"))
    with pytest.raises(ValueError, match="score_mode"):
        _score(adapter, {})


# ---------------------------------------------------------------------------
# domain: the evolution loop under the soft-label lens
# ---------------------------------------------------------------------------
def _outcome(cid, benchmark, holdout, gate):
    return CandidateOutcome(
        candidate_id=cid, benchmark_score=benchmark,
        holdout_score=holdout, gate=gate,
    )


def test_domain_detects_gate_adverse_selection():
    # Gate accepts high-benchmark/low-holdout candidates (Goodhart) and
    # rejects an honestly better one.
    outcomes = [
        _outcome("c1", 0.9, 0.3, GateDecision.ACCEPTED),
        _outcome("c2", 0.85, 0.35, GateDecision.ACCEPTED),
        _outcome("c3", 0.4, 0.8, GateDecision.ROLLED_BACK),
        _outcome("c4", 0.2, None, GateDecision.PENDING),  # ignored
    ]
    report = AevolveEvolutionAdapter().from_outcomes(outcomes)
    assert report.n_candidates == 3
    assert report.n_accepted == 2
    assert report.quality_gap < 0
    assert report.adverse_selection


def test_domain_healthy_gate_shows_positive_gap():
    outcomes = [
        _outcome("c1", 0.9, 0.85, GateDecision.ACCEPTED),
        _outcome("c2", 0.3, 0.2, GateDecision.ROLLED_BACK),
    ]
    report = AevolveEvolutionAdapter().from_outcomes(outcomes)
    assert report.quality_gap > 0
    assert not report.adverse_selection


def test_domain_shrinks_train_scores_toward_neutral():
    adapter = AevolveEvolutionAdapter()
    trusted = adapter.candidate_p(_outcome("c", 0.9, 0.9, GateDecision.ACCEPTED))
    shrunk = adapter.candidate_p(_outcome("c", 0.9, None, GateDecision.ACCEPTED))
    assert trusted == 0.9
    assert 0.5 < shrunk < 0.9  # self-graded score gets less credence
    # p always bounded even for out-of-range inputs.
    assert adapter.candidate_p(_outcome("c", 2.0, None, GateDecision.ACCEPTED)) <= 1.0
