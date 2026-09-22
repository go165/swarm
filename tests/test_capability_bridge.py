"""Capability precondition lever and the prevention-vs-detection bridge (bead vwj3)."""

import pytest

from swarm.env.state import EnvState
from swarm.governance.capability_precondition import (
    RESOURCE_KEY,
    CapabilityPreconditionLever,
)
from swarm.governance.config import GovernanceConfig
from swarm.models.interaction import SoftInteraction
from swarm.redteam.audit_bridge import audit_catch_probability
from swarm.redteam.capability_bridge import per_step_refusal, simulate_attack

AUDIT = GovernanceConfig(audit_enabled=True, audit_probability=0.4, audit_threshold_p=0.5)


def _write(initiator, resource, p=0.9):
    return SoftInteraction(initiator=initiator, p=p, accepted=True, metadata={RESOURCE_KEY: resource})


class TestLever:
    def test_refuses_outside_grant_whatever_p(self):
        lever = CapabilityPreconditionLever(grants={"a": {"repo"}})
        for p in (0.01, 0.5, 0.99):
            assert lever.on_interaction(_write("a", "secrets", p), EnvState()).details["refused"]
        assert lever.refusals == 3

    def test_allows_granted_resource_and_unscoped_interactions(self):
        lever = CapabilityPreconditionLever(grants={"a": {"repo"}})
        assert not lever.on_interaction(_write("a", "repo", p=0.01), EnvState()).details["refused"]
        assert not lever.on_interaction(SoftInteraction(initiator="a"), EnvState()).details["refused"]
        assert lever.refusals == 0

    def test_refusal_costs_nothing(self):
        lever = CapabilityPreconditionLever(grants={})
        effect = lever.on_interaction(_write("a", "repo"), EnvState())
        assert effect.cost_a == 0.0 and not effect.reputation_deltas


class TestShapes:
    @pytest.mark.parametrize("p_int", [0.2, 0.49, 0.5, 0.8])
    def test_refusal_is_flat_in_p(self, p_int):
        assert per_step_refusal(p_int) == 1.0
        assert per_step_refusal(p_int, out_of_grant=False) == 0.0

    def test_audit_catch_is_a_cliff_at_the_threshold(self):
        assert audit_catch_probability(AUDIT, 0.49, n_samples=2000) > 0.3
        assert audit_catch_probability(AUDIT, 0.5, n_samples=2000) == 0.0


class TestSimulateAttack:
    def test_precondition_blocks_exactly_the_out_of_grant_fraction(self):
        for coverage in (0.0, 0.25, 0.5, 1.0):
            h = simulate_attack(AUDIT, 0.8, coverage, k=20, n_trials=50)
            assert h.precondition == pytest.approx(1.0 - coverage)

    def test_clean_attacker_blinds_the_audit(self):
        h = simulate_attack(AUDIT, 0.8, 0.25, k=20, n_trials=200)
        assert h.audit == 1.0 and h.audit_halt_rate == 0.0
        assert h.both == pytest.approx(h.precondition)

    def test_dirty_attacker_is_halted_by_the_audit(self):
        h = simulate_attack(AUDIT, 0.3, 0.0, k=20, n_trials=500)
        assert h.audit < 0.2 and h.audit_halt_rate > 0.95

    def test_single_step_attack_always_completes_under_audit(self):
        # The audit scores a step after it executes; halting cannot undo it.
        assert simulate_attack(AUDIT, 0.3, 0.0, k=1, n_trials=200).audit == 1.0

    def test_both_is_never_worse_than_either(self):
        for p in (0.3, 0.8):
            for c in (0.0, 0.5, 1.0):
                h = simulate_attack(AUDIT, p, c, k=10, n_trials=200)
                assert h.both <= min(h.audit, h.precondition) + 1e-9

    def test_deterministic_for_a_seed(self):
        assert simulate_attack(AUDIT, 0.3, 0.5, k=10, n_trials=100, seed=7) == \
            simulate_attack(AUDIT, 0.3, 0.5, k=10, n_trials=100, seed=7)

    def test_rejects_bad_coverage(self):
        with pytest.raises(ValueError):
            simulate_attack(AUDIT, 0.3, 1.5)
