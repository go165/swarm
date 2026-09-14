"""Capability precondition: refuse writes outside an agent's grant (bead vwj3).

The prevention counterpart to the detection levers. ``RandomAuditLever`` scores
an interaction after the fact and penalizes it only if its proxy label ``p``
falls below a threshold, so an attacker who keeps each step clean slips under
it. This lever checks *authority*, not suspiciousness: a write to a resource
the agent was not granted is refused whatever its ``p``, so decomposing an
unauthorized write into many small ones yields many refusals.

It covers only what is expressible as a capability boundary. A harmful write
to a resource the agent *is* granted passes, which is most of what SWARM
studies. Not wired into ``GovernanceEngine``: it is used directly by
``swarm/redteam/capability_bridge.py`` to compare robustness shapes.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Set

from swarm.env.state import EnvState
from swarm.governance.config import GovernanceConfig
from swarm.governance.levers import GovernanceLever, LeverEffect
from swarm.models.interaction import SoftInteraction

# Interaction metadata key naming the resource an interaction writes to.
RESOURCE_KEY = "resource"


class CapabilityPreconditionLever(GovernanceLever):
    def __init__(
        self,
        config: Optional[GovernanceConfig] = None,
        grants: Optional[Mapping[str, Iterable[str]]] = None,
    ):
        super().__init__(config or GovernanceConfig())
        self._grants: Dict[str, Set[str]] = {a: set(r) for a, r in (grants or {}).items()}
        self.refusals = 0

    @property
    def name(self) -> str:
        return "capability_precondition"

    def authorize(self, agent_id: str, resource: str) -> bool:
        """True iff ``resource`` is in ``agent_id``'s grant."""
        return resource in self._grants.get(agent_id, set())

    def on_interaction(self, interaction: SoftInteraction, state: EnvState) -> LeverEffect:
        """Refuse an interaction that writes outside the initiator's grant.

        Refusal is reported in ``details``; there is no cost, because the write
        never happens. Interactions that name no resource are out of scope.
        """
        resource = (interaction.metadata or {}).get(RESOURCE_KEY)
        if resource is None or self.authorize(interaction.initiator, resource):
            return LeverEffect(lever_name=self.name, details={"refused": False})
        self.refusals += 1
        return LeverEffect(lever_name=self.name, details={"refused": True, "resource": resource})
