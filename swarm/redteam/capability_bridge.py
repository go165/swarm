"""Prevention vs detection under decomposition, with real levers (bead vwj3).

``audit_bridge`` (bead 3ru4) showed the real ``RandomAuditLever``'s catch
probability collapses to exactly 0 once an attacker keeps each interaction's
proxy label above ``audit_threshold_p``. This bridge runs the same attacker
through ``CapabilityPreconditionLever`` as well, to compare robustness shapes
on the same axis.

Attacker model: an objective split into ``k`` equal steps, each with proxy
label ``p_int`` (a better-decomposing attacker has cleaner steps). A fraction
``coverage`` of the steps write to resources outside the attacker's grant;
the rest are harmful writes to resources it is granted. Harm realized is the
fraction of steps that execute:

- **precondition**: out-of-grant steps are refused and never execute; granted
  steps pass. It never halts the attack.
- **audit**: every executing step goes through the audit; the first penalty
  halts the attack, and the remaining steps never execute.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from swarm.env.state import EnvState
from swarm.governance.audits import RandomAuditLever
from swarm.governance.capability_precondition import (
    RESOURCE_KEY,
    CapabilityPreconditionLever,
)
from swarm.governance.config import GovernanceConfig
from swarm.models.interaction import InteractionType, SoftInteraction

ATTACKER = "attacker"
GRANTED = "granted_resource"
UNGRANTED = "ungranted_resource"


def per_step_refusal(p_int: float, out_of_grant: bool = True) -> float:
    """Refusal probability of the real precondition lever for one step.

    Takes ``p_int`` only to make the point that it does not enter: the lever
    reads the resource, not the proxy label."""
    lever = CapabilityPreconditionLever(grants={ATTACKER: {GRANTED}})
    step = _step(p_int, UNGRANTED if out_of_grant else GRANTED)
    return float(lever.on_interaction(step, EnvState()).details["refused"])


def _step(p_int: float, resource: str) -> SoftInteraction:
    return SoftInteraction(
        initiator=ATTACKER,
        counterparty="victim",
        interaction_type=InteractionType.COLLABORATION,
        accepted=True,
        p=p_int,
        metadata={RESOURCE_KEY: resource},
    )


@dataclass(frozen=True)
class HarmOutcome:
    """Mean fraction of the attacker's ``k`` steps that execute."""

    unguarded: float
    precondition: float
    audit: float
    both: float
    audit_halt_rate: float  # fraction of attacks the audit stopped at all


def simulate_attack(
    config: GovernanceConfig,
    p_int: float,
    coverage: float,
    k: int = 10,
    n_trials: int = 2000,
    seed: int = 0,
) -> HarmOutcome:
    """Monte Carlo harm realized under each lever arrangement, real levers.

    Out-of-grant steps are spread evenly through the sequence
    (``round(coverage * k)`` of them), so the audit meets both kinds.
    """
    if not 0.0 <= coverage <= 1.0:
        raise ValueError("coverage must be in [0, 1]")
    n_out = round(coverage * k)
    # Even spacing: step i is out of grant iff it crosses a multiple of k/n_out.
    out = [n_out > 0 and (i * n_out) // k != ((i + 1) * n_out) // k for i in range(k)]
    state = EnvState()
    state.add_agent(ATTACKER, initial_resources=100.0)
    rng = random.Random(seed)
    totals = {"precondition": 0.0, "audit": 0.0, "both": 0.0}
    halts = 0
    for _ in range(n_trials):
        trial_seed = rng.randrange(2**31)
        for arm in ("audit", "both"):
            audit = RandomAuditLever(config, seed=trial_seed)
            gate = CapabilityPreconditionLever(grants={ATTACKER: {GRANTED}}) if arm == "both" else None
            executed, halted = _run(audit, gate, p_int, out, state)
            totals[arm] += executed / k
            if arm == "audit" and halted:
                halts += 1
        gate = CapabilityPreconditionLever(grants={ATTACKER: {GRANTED}})
        executed, _ = _run(None, gate, p_int, out, state)
        totals["precondition"] += executed / k
    return HarmOutcome(
        unguarded=1.0,
        precondition=totals["precondition"] / n_trials,
        audit=totals["audit"] / n_trials,
        both=totals["both"] / n_trials,
        audit_halt_rate=halts / n_trials,
    )


def _run(
    audit: Optional[RandomAuditLever],
    gate: Optional[CapabilityPreconditionLever],
    p_int: float,
    out_of_grant: list,
    state: EnvState,
) -> tuple:
    executed = 0
    for is_out in out_of_grant:
        step = _step(p_int, UNGRANTED if is_out else GRANTED)
        if gate is not None and gate.on_interaction(step, state).details["refused"]:
            continue
        executed += 1
        if audit is not None and audit.on_interaction(step, state).details.get("penalty_applied"):
            return executed, True
    return executed, False
