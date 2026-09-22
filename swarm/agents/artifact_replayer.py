"""Artifact replayer: launders low-quality work with someone else's receipt (bead iujo).

Its own interactions draw adversarial observables, so its honest record is
poor. When ``replay`` is on it presents the highest-``p`` receipt it can see
from another producer, so a counterparty that trusts receipts accepts on a
quality signal earned in a different interaction. With ``replay: false`` it
proposes the same way but presents nothing, which is the control arm.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from swarm.agents.base import Action, BaseAgent, InteractionProposal, Observation, Role
from swarm.governance.artifact_replay import PRESENTED_KEY, RECEIPT_KIND
from swarm.models.agent import AgentType
from swarm.models.interaction import InteractionType


class ArtifactReplayerAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        roles: Optional[List[Role]] = None,
        config: Optional[Dict] = None,
        name: Optional[str] = None,
        rng=None,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.ADVERSARIAL,
            roles=roles,
            config=config or {},
            name=name,
            rng=rng,
        )
        self.replay = bool(self.config.get("replay", True))
        self.interact_probability = self.config.get("interact_probability", 0.6)

    def _best_foreign_receipt(self, observation: Observation, target_id: str) -> Optional[str]:
        """Highest-p receipt produced by neither this agent nor the target.

        The target is excluded because a counterparty cannot see its own
        receipts in its observation, so presenting one would be ignored.
        """
        receipts = [
            a for a in observation.available_artifacts
            if a.get("kind") == RECEIPT_KIND and a.get("producer_id") not in (self.agent_id, target_id)
        ]
        if not receipts:
            return None
        best = max(receipts, key=lambda a: (a.get("p_at_production", 0.0), a.get("artifact_id", "")))
        return str(best["artifact_id"])

    def act(self, observation: Observation) -> Action:
        targets = sorted(
            a.get("agent_id", "") for a in observation.visible_agents
            if a.get("agent_id") and a.get("agent_id") != self.agent_id
        )
        if not (observation.can_interact and targets) or self._rng.random() >= self.interact_probability:
            return self.create_noop_action()
        target = targets[self._rng.randrange(len(targets))]
        action = self.create_propose_action(
            counterparty_id=target,
            interaction_type=InteractionType.COLLABORATION,
            content="Would you like to collaborate?",
        )
        if self.replay:
            receipt = self._best_foreign_receipt(observation, target)
            if receipt is not None:
                action.metadata[PRESENTED_KEY] = receipt
        return action

    def accept_interaction(self, proposal: InteractionProposal, observation: Observation) -> bool:
        return True

    def propose_interaction(
        self, observation: Observation, counterparty_id: str
    ) -> Optional[InteractionProposal]:
        return InteractionProposal(
            initiator_id=self.agent_id,
            counterparty_id=counterparty_id,
            interaction_type=InteractionType.COLLABORATION,
            content="Would you like to collaborate?",
        )
