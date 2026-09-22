"""Artifact replay levers, replayer agent, and scenario (bead iujo)."""

import copy

import pytest

from swarm.agents.artifact_replayer import ArtifactReplayerAgent
from swarm.agents.base import InteractionProposal, Observation
from swarm.agents.honest import HonestAgent
from swarm.env.state import EnvState
from swarm.governance.artifact_replay import (
    BLOCKED_KEY,
    PRESENTED_KEY,
    RECEIPT_KIND,
    ArtifactContextBindingLever,
    ArtifactReceiptLever,
    ArtifactReplayDetectorLever,
    is_replay,
)
from swarm.governance.config import GovernanceConfig
from swarm.governance.engine import GovernanceEngine
from swarm.models.artifact import Artifact
from swarm.models.interaction import SoftInteraction
from swarm.scenarios import build_orchestrator, load_scenario


def _state_with_receipt(producer="honest_1", p=0.9):
    state = EnvState()
    receipt = Artifact(kind=RECEIPT_KIND, producer_id=producer, p_at_production=p)
    state.artifact_registry.publish(receipt)
    return state, receipt


def _interaction(initiator, metadata=None, accepted=True, p=0.2):
    return SoftInteraction(initiator=initiator, counterparty="honest_2", accepted=accepted,
                           p=p, metadata=dict(metadata or {}))


class TestIsReplay:
    def test_foreign_receipt_is_a_replay(self):
        state, receipt = _state_with_receipt()
        assert is_replay({PRESENTED_KEY: receipt.artifact_id}, "artifact_replayer_1", state)

    def test_own_receipt_or_no_receipt_is_not(self):
        state, receipt = _state_with_receipt()
        assert not is_replay({PRESENTED_KEY: receipt.artifact_id}, "honest_1", state)
        assert not is_replay({}, "artifact_replayer_1", state)
        assert not is_replay({PRESENTED_KEY: "unknown"}, "artifact_replayer_1", state)


class TestReceipts:
    def test_publishes_only_for_accepted_interactions_when_enabled(self):
        state = EnvState()
        lever = ArtifactReceiptLever(GovernanceConfig(artifact_receipts_enabled=True))
        lever.on_interaction(_interaction("honest_1", p=0.8), state)
        lever.on_interaction(_interaction("honest_1", accepted=False), state)
        receipts = list(state.artifact_registry._artifacts.values())
        assert [(r.producer_id, r.p_at_production) for r in receipts] == [("honest_1", 0.8)]

    def test_disabled_publishes_nothing(self):
        state = EnvState()
        ArtifactReceiptLever(GovernanceConfig()).on_interaction(_interaction("honest_1"), state)
        assert not state.artifact_registry._artifacts


class TestBinding:
    def test_strips_foreign_receipt_and_marks_it(self):
        state, receipt = _state_with_receipt()
        meta = {PRESENTED_KEY: receipt.artifact_id}
        ArtifactContextBindingLever(
            GovernanceConfig(artifact_context_binding_enabled=True)
        ).screen_presentation(meta, "artifact_replayer_1", state)
        assert PRESENTED_KEY not in meta and meta[BLOCKED_KEY] is True

    def test_keeps_own_receipt(self):
        state, receipt = _state_with_receipt()
        meta = {PRESENTED_KEY: receipt.artifact_id}
        ArtifactContextBindingLever(
            GovernanceConfig(artifact_context_binding_enabled=True)
        ).screen_presentation(meta, "honest_1", state)
        assert meta == {PRESENTED_KEY: receipt.artifact_id}

    def test_engine_screens_only_when_enabled(self):
        state, receipt = _state_with_receipt()
        meta = {PRESENTED_KEY: receipt.artifact_id}
        GovernanceEngine(GovernanceConfig()).screen_artifact_presentation(meta, "artifact_replayer_1", state)
        assert PRESENTED_KEY in meta


class TestDetector:
    def test_catches_replays_at_rate_one_and_penalizes_initiator(self):
        state, receipt = _state_with_receipt()
        lever = ArtifactReplayDetectorLever(GovernanceConfig(
            artifact_replay_detection_enabled=True, artifact_replay_detection_rate=1.0,
            artifact_replay_false_positive_rate=0.0, artifact_replay_penalty=2.0))
        effect = lever.on_interaction(
            _interaction("artifact_replayer_1", {PRESENTED_KEY: receipt.artifact_id}), state)
        assert effect.cost_a == 2.0
        assert effect.reputation_deltas == {"artifact_replayer_1": -2.0}
        assert (lever.caught_replays, lever.false_positives) == (1, 0)

    def test_false_positives_hit_clean_interactions(self):
        state, _ = _state_with_receipt()
        lever = ArtifactReplayDetectorLever(GovernanceConfig(
            artifact_replay_detection_enabled=True, artifact_replay_false_positive_rate=1.0))
        effect = lever.on_interaction(_interaction("honest_3"), state)
        assert effect.cost_a == 1.0 and lever.false_positives == 1

    def test_rejected_interactions_are_ignored(self):
        state, receipt = _state_with_receipt()
        lever = ArtifactReplayDetectorLever(GovernanceConfig(
            artifact_replay_detection_enabled=True, artifact_replay_detection_rate=1.0))
        effect = lever.on_interaction(_interaction(
            "artifact_replayer_1", {PRESENTED_KEY: receipt.artifact_id}, accepted=False), state)
        assert effect.cost_a == 0.0

    @pytest.mark.parametrize("field,value", [
        ("artifact_replay_detection_rate", 1.5),
        ("artifact_replay_false_positive_rate", -0.1),
        ("artifact_replay_penalty", -1.0),
    ])
    def test_config_validation(self, field, value):
        with pytest.raises(ValueError):
            GovernanceConfig(**{field: value})


class TestAgents:
    def _obs(self, *artifacts):
        return Observation(available_artifacts=[a.to_dict() for a in artifacts],
                           visible_agents=[{"agent_id": "honest_2"}], can_interact=True)

    def test_honest_trusts_presented_receipt_only_when_configured(self):
        receipt = Artifact(kind=RECEIPT_KIND, producer_id="honest_1", p_at_production=0.95)
        proposal = InteractionProposal(initiator_id="artifact_replayer_1", counterparty_id="honest_2",
                                       metadata={PRESENTED_KEY: receipt.artifact_id})
        cfg = {"trust_weight": 1.0, "acceptance_threshold": 0.9}
        trusting = HonestAgent("honest_2", config=dict(cfg, trust_artifacts=True))
        plain = HonestAgent("honest_2", config=cfg)
        assert trusting.accept_interaction(proposal, self._obs(receipt))
        assert not plain.accept_interaction(proposal, self._obs(receipt))

    def test_honest_falls_back_to_initiators_own_receipts(self):
        own = Artifact(kind=RECEIPT_KIND, producer_id="artifact_replayer_1", p_at_production=0.1)
        other = Artifact(kind=RECEIPT_KIND, producer_id="honest_1", p_at_production=0.95)
        proposal = InteractionProposal(initiator_id="artifact_replayer_1", counterparty_id="honest_2")
        assert HonestAgent._receipt_p(proposal, self._obs(own, other)) == 0.1

    def test_replayer_presents_best_foreign_receipt_not_targets_own(self):
        mine = Artifact(kind=RECEIPT_KIND, producer_id="artifact_replayer_1", p_at_production=0.99)
        targets = Artifact(kind=RECEIPT_KIND, producer_id="honest_2", p_at_production=0.98)
        best = Artifact(kind=RECEIPT_KIND, producer_id="honest_1", p_at_production=0.9)
        agent = ArtifactReplayerAgent("artifact_replayer_1", config={"interact_probability": 1.0})
        action = agent.act(self._obs(mine, targets, best))
        assert action.counterparty_id == "honest_2"
        assert action.metadata[PRESENTED_KEY] == best.artifact_id

    def test_replayer_with_replay_off_presents_nothing(self):
        best = Artifact(kind=RECEIPT_KIND, producer_id="honest_1", p_at_production=0.9)
        agent = ArtifactReplayerAgent("artifact_replayer_3", config={"replay": False, "interact_probability": 1.0})
        assert PRESENTED_KEY not in agent.act(self._obs(best)).metadata


class TestScenario:
    def test_yaml_parses_levers_and_roster(self):
        scenario = load_scenario("scenarios/artifact_replay.yaml")
        gc = scenario.orchestrator_config.governance_config
        assert gc.artifact_receipts_enabled
        assert not gc.artifact_context_binding_enabled and not gc.artifact_replay_detection_enabled
        assert (gc.artifact_replay_detection_rate, gc.artifact_replay_false_positive_rate,
                gc.artifact_replay_penalty) == (0.5, 0.05, 1.0)

    def test_binding_stops_replayed_receipts_reaching_acceptance(self):
        scenario = load_scenario("scenarios/artifact_replay.yaml")
        scenario.orchestrator_config.governance_config.artifact_context_binding_enabled = True
        scenario.orchestrator_config.n_epochs = 3
        orch = build_orchestrator(copy.deepcopy(scenario))
        presented, blocked = [], []
        orch.on_interaction_complete(lambda i, *_: (
            presented.append(i) if (i.metadata or {}).get(PRESENTED_KEY) and
            i.initiator.startswith("artifact_replayer") else None,
            blocked.append(i) if (i.metadata or {}).get(BLOCKED_KEY) else None))
        orch.run()
        assert blocked, "replayers should have tried to present foreign receipts"
        assert not presented
