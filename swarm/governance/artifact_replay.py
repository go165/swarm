"""Artifact replay governance: receipts, context binding, replay detection (bead iujo).

A receipt carries the soft label ``p`` of the interaction that produced it. If
another agent can present that receipt, a counterparty's accept decision
conditions on quality earned somewhere else. Three levers, each switched on
independently so a scenario can isolate one:

- ``ArtifactReceiptLever`` publishes a receipt for every accepted interaction.
- ``ArtifactContextBindingLever`` (prevention) strips a presented receipt whose
  producer is not the presenter, *before* the accept decision.
- ``ArtifactReplayDetectorLever`` (detection) penalizes replayed presentations
  it catches *after* acceptance, with a false-positive rate on everything else.

See docs/research/artifact-replay-prevention-vs-detection.md.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional

from swarm.env.state import EnvState
from swarm.governance.config import GovernanceConfig
from swarm.governance.levers import GovernanceLever, LeverEffect
from swarm.models.artifact import Artifact
from swarm.models.interaction import SoftInteraction

RECEIPT_KIND = "receipt"
# Proposal / interaction metadata key naming the receipt an initiator presents.
PRESENTED_KEY = "presented_artifact_id"
# Set on the metadata when binding strips a presentation.
BLOCKED_KEY = "artifact_presentation_blocked"


def _global_step(state: EnvState) -> int:
    return state.current_epoch * state.steps_per_epoch + state.current_step


def is_replay(metadata: Dict[str, Any], initiator_id: str, state: EnvState) -> bool:
    """True when the metadata presents a known receipt someone else produced."""
    artifact_id = metadata.get(PRESENTED_KEY)
    if not artifact_id:
        return False
    artifact = state.artifact_registry.get(artifact_id)
    return artifact is not None and artifact.producer_id != initiator_id


class ArtifactReceiptLever(GovernanceLever):
    """Publish a receipt stamped with ``p`` for each accepted interaction."""

    @property
    def name(self) -> str:
        return "artifact_receipts"

    def on_interaction(self, interaction: SoftInteraction, state: EnvState) -> LeverEffect:
        if self.config.artifact_receipts_enabled and interaction.accepted:
            state.artifact_registry.publish(
                Artifact(
                    kind=RECEIPT_KIND,
                    producer_id=interaction.initiator,
                    interaction_id=interaction.interaction_id,
                    step=_global_step(state),
                    p_at_production=interaction.p,
                )
            )
        return LeverEffect(lever_name=self.name)


class ArtifactContextBindingLever(GovernanceLever):
    """Prevention: a receipt is only honoured when its presenter produced it."""

    @property
    def name(self) -> str:
        return "artifact_context_binding"

    def screen_presentation(
        self, metadata: Dict[str, Any], initiator_id: str, state: EnvState
    ) -> None:
        """Strip a replayed presentation from ``metadata`` in place.

        In place so the interaction record the finalizer builds from the same
        proposal metadata shows what the counterparty actually saw.
        """
        if self.config.artifact_context_binding_enabled and is_replay(
            metadata, initiator_id, state
        ):
            metadata.pop(PRESENTED_KEY)
            metadata[BLOCKED_KEY] = True


class ArtifactReplayDetectorLever(GovernanceLever):
    """Detection: catch replays after acceptance, at a cost to false positives."""

    def __init__(self, config: GovernanceConfig, seed: Optional[int] = None):
        super().__init__(config)
        self._rng = random.Random(seed)
        # Tallies for sweeps: replays caught vs clean interactions flagged.
        self.caught_replays = 0
        self.false_positives = 0

    @property
    def name(self) -> str:
        return "artifact_replay_detection"

    def on_interaction(self, interaction: SoftInteraction, state: EnvState) -> LeverEffect:
        if not self.config.artifact_replay_detection_enabled or not interaction.accepted:
            return LeverEffect(lever_name=self.name)
        replay = is_replay(interaction.metadata or {}, interaction.initiator, state)
        rate = (
            self.config.artifact_replay_detection_rate
            if replay
            else self.config.artifact_replay_false_positive_rate
        )
        # Always draw, so the RNG stream does not depend on which branch ran.
        flagged = self._rng.random() < rate
        if not flagged:
            return LeverEffect(lever_name=self.name, details={"replay": replay, "flagged": False})
        if replay:
            self.caught_replays += 1
        else:
            self.false_positives += 1
        penalty = self.config.artifact_replay_penalty
        return LeverEffect(
            cost_a=penalty,
            reputation_deltas={interaction.initiator: -penalty},
            lever_name=self.name,
            details={"replay": replay, "flagged": True, "false_positive": not replay},
        )
