"""Configuration for the SWARM ↔ A-Evolve benchmark bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# Governance/payoff knobs an evolved candidate may override. Everything else
# in the scenario (agent mix, epochs, seed, success criteria) is fixed by the
# benchmark — an agent that could shrink the simulation or delete the
# deceptive agents would be gaming the harness, not designing governance.
# The audit and breaker thresholds are whitelisted because their defaults
# (freeze at toxicity 0.7, audit 10% below p=0.5) never trigger at this
# benchmark's scale: enabling either lever without tuning it scored exactly
# the null candidate (beads 2qgp, sw83).
DEFAULT_ALLOWED_OVERRIDES: Tuple[str, ...] = (
    "governance.transaction_tax_rate",
    "governance.transaction_tax_split",
    "governance.reputation_decay_rate",
    "governance.bandwidth_cap",
    "governance.staking_enabled",
    "governance.min_stake_to_participate",
    "governance.circuit_breaker_enabled",
    "governance.freeze_threshold_toxicity",
    "governance.freeze_threshold_violations",
    "governance.freeze_duration_epochs",
    "governance.audit_enabled",
    "governance.audit_probability",
    "governance.audit_threshold_p",
    "governance.audit_penalty_multiplier",
    "payoff.theta",
    "payoff.rho_a",
    "payoff.rho_b",
    "payoff.w_rep",
)


@dataclass
class AevolveBridgeConfig:
    """Knobs for :class:`~swarm.bridges.aevolve.adapter.SwarmBenchmarkAdapter`.

    ``score_mode``:

    - ``welfare_weighted`` (default): ``(1 - toxicity) * W / (W + welfare_scale)``
      with ``W = max(0, total_welfare)`` from the final epoch. Clean accepted
      interactions only count if the market still produces welfare, so a
      candidate cannot score by shutting the market down (a stake above every
      agent's resources used to score 1.0), and levers that trade welfare for
      toxicity register on both sides.
    - ``one_minus_toxicity``: ``1 - E[1-p | accepted]`` from the final epoch;
      0.0 when nothing was accepted, since toxicity is then undefined.
    - ``s_soft``: mean expected surplus per interaction, squashed to [0, 1]
      via ``score = 1 / (1 + exp(-S_soft))`` so Feedback stays in range.
    """

    scenario_path: str = "scenarios/aevolve_screening.yaml"
    n_tasks: int = 4  # tasks are (scenario, seed) cells: seed_base + index
    seed_base: int = 1000
    holdout_seed_base: int = 9000  # disjoint seeds for split="holdout"/"test"
    score_mode: str = "welfare_weighted"  # or "one_minus_toxicity", "s_soft"
    welfare_scale: float = 10.0  # welfare at which welfare_weighted halves (1 - toxicity)
    # Under welfare_weighted the ungoverned screening scenario scores about
    # 0.36, so success means clearly beating no governance at all.
    success_threshold: float = 0.4
    # Keep evolution cycles cheap: cap the simulation size regardless of what
    # the scenario file says. None = respect the scenario.
    max_epochs: Optional[int] = 5
    max_steps_per_epoch: Optional[int] = 10
    allowed_overrides: Tuple[str, ...] = DEFAULT_ALLOWED_OVERRIDES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_path": self.scenario_path,
            "n_tasks": self.n_tasks,
            "seed_base": self.seed_base,
            "holdout_seed_base": self.holdout_seed_base,
            "score_mode": self.score_mode,
            "welfare_scale": self.welfare_scale,
            "success_threshold": self.success_threshold,
            "max_epochs": self.max_epochs,
            "max_steps_per_epoch": self.max_steps_per_epoch,
            "allowed_overrides": list(self.allowed_overrides),
        }


@dataclass
class EvaluationDetail:
    """Everything the evolver gets to see about one evaluated candidate."""

    scenario_id: str = ""
    seed: int = 0
    applied_overrides: Dict[str, Any] = field(default_factory=dict)
    rejected_overrides: Dict[str, Any] = field(default_factory=dict)
    toxicity: float = 0.0
    quality_gap: float = 0.0
    total_welfare: float = 0.0
    total_interactions: int = 0
    accepted_interactions: int = 0
    parse_error: str = ""

    def to_text(self) -> str:
        """Rich diagnostic text for ``Feedback.detail`` (evolver-facing)."""
        if self.parse_error:
            return (
                f"REJECTED: {self.parse_error}. Emit a JSON object of "
                f"governance overrides, e.g. "
                f'{{"governance.transaction_tax_rate": 0.1}}.'
            )
        lines = [
            f"scenario={self.scenario_id} seed={self.seed}",
            f"applied_overrides={self.applied_overrides}",
        ]
        if self.rejected_overrides:
            lines.append(
                f"rejected_overrides (not in whitelist): {self.rejected_overrides}"
            )
        lines.append(
            f"final epoch: toxicity={self.toxicity:.4f} "
            f"quality_gap={self.quality_gap:+.4f} "
            f"welfare={self.total_welfare:.2f} "
            f"interactions={self.total_interactions} "
            f"({self.accepted_interactions} accepted)"
        )
        if self.quality_gap < 0:
            lines.append(
                "adverse selection present: accepted interactions are lower-"
                "quality than rejected ones — governance is selecting badly"
            )
        return "\n".join(lines)
