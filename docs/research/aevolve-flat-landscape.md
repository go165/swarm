# The A-Evolve benchmark has no gradient over behavior (3o9l recon → 2qgp)

**Beads:** 3o9l (adversary evolution track — recon), 2qgp (the bug it surfaced)
**Date:** 2026-07-27
**Reproducer:** `experiments/aevolve_landscape_probe.py` (deterministic, seeded)
**Verifies:** ni9b (A-Evolve bridge, closed unverified) per the 3o9l recon
protocol: *"before building on it, confirm diverse attack phenotypes / evolved
S_soft < random baseline."*

## Verdict: the precondition fails — do not build the evolution track yet

3o9l wants to evolve `AdaptiveAdversary` agents to exploit weak governance. An
evolution engine only produces meaningful results if distinct candidate
configurations produce distinct fitness. On the `aevolve_screening` scenario
they do not.

## Evidence

`python experiments/aevolve_landscape_probe.py` (5 seeds, deterministic):

**Attacker landscape** — vary `AdaptiveAdversary` knobs, fixed weak governance:

| phenotype | exploration/learning/heat | toxicity | payoff | welfare |
|---|---|---|---|---|
| passive | 0.0 / 0.0 / 1.0 | 0.3230 | +0.515 | 8.67 |
| default | (defaults) | 0.3230 | +0.515 | 8.67 |
| aggressive | 0.5 / 0.5 / 0.9 | 0.3230 | +0.515 | 8.67 |
| stealth | 0.1 / 0.3 / 0.2 | 0.3230 | +0.515 | 8.67 |

Knob toxicity spread: **0.0000**. Every behavioral configuration produces a
byte-identical outcome.

**Control** — vary the agent *mix* instead of the knobs:

| mix | toxicity |
|---|---|
| 0 deceptive (6 honest) | 0.2325 |
| 1 deceptive | 0.3236 |
| 4 deceptive | 0.3681 |
| 4 adaptive_adversary | 0.3620 |

Mix toxicity spread: **0.1356**. The harness moves — but on agent *type/count*,
and `4 adaptive_adversary ≈ 4 deceptive`.

**Defender landscape** (ni9b's own direction) — governance phenotypes through
`SwarmBenchmarkAdapter`: `staking_enabled`, `min_stake_to_participate`,
`audit_enabled`, `circuit_breaker_enabled`, and `payoff.theta` each score
**exactly equal to the null candidate** (0.668). Only `transaction_tax` and
`rho_a/rho_b` move welfare, and the default `one_minus_toxicity` score barely
reflects even those (spread 0.0045).

## Correction (2026-09-13): the attacker root cause was a lay-low bug

The root cause below is wrong for the attacker side. `AdversaryMemory`
initialised `epochs_since_detection = 0`, and `_should_lay_low` treats `< 2`
as "recently detected". The counter only advances inside
`update_adversary_outcome`, which nothing in the run loop calls. So the
adversary took `_act_innocently` on 96 of 96 turns: its strategy code never
ran, and exploration/learning/heat could not change anything. With the
counters starting at a "never detected" sentinel, the same probe gives:

| phenotype | toxicity | payoff | welfare |
|---|---|---|---|
| passive | 0.4288 | +0.357 | 9.24 |
| default | 0.4139 | +0.379 | 8.25 |
| aggressive | 0.4178 | +0.373 | 8.50 |
| stealth | 0.4444 | +0.333 | 7.86 |

Knob toxicity spread is **0.0304** (was 0.0000). The gate
`test_attacker_knobs_have_gradient` now passes. Two knobs are still inert:
`learning_rate` is stored and never read, and `heat_threshold` only matters
once detections are reported, which still needs the orchestrator to call
`notify_adversary_detection`.

The defender side is a different problem. The levers are wired: the override
reaches every lever's config. They just never trigger at this scenario's
scale. Across 5 seeds with all of them on: 25 audits and 0 penalties (7 of
215 interactions had `p < audit_threshold_p = 0.5`, none of them audited); 0
freezes (no interaction has `p < 0.3`, so `freeze_threshold_toxicity = 0.7`
is unreachable); minimum agent resources stayed at 100, so a stake of 5 never
binds. `theta` only splits surplus, so it cannot move toxicity or total
welfare by construction.

## Original root cause (superseded for the attacker side)

`p` (and therefore toxicity, payoff, welfare) is a function of agent
**type/count**, not of the actions an agent actually takes. The
`AdaptiveAdversary` runs its bandit/heat/exploration logic and emits actions,
but those actions do not change the observable distribution the
`ProxyComputer` sees for that agent — the proxy is keyed on the agent's type.
So the whole learned-behavior surface the evolution track would search over is
invisible to fitness. Same mechanism kills the boolean governance levers on the
defender side: they gate on inner conditions (audit probability, funded stake,
breaker triggers) that never fire in a 5×10 sim, so they too collapse onto the
null score.

## Disposition

- **2qgp** (filed P2) owns the fix: make agent behavior propagate to the soft
  labels (or, minimally, give the benchmark a scenario where it does), and
  blend welfare into the score mode so the levers that *do* move welfare
  register. The reproducer is its replayable gate; `test_aevolve_landscape_
  probe.py::test_attacker_knobs_have_gradient` is a strict `xfail` that flips
  to `xpass` when the gradient appears.
- **3o9l** stays OPEN, blocked on 2qgp. Building an `EvolutionEngine` over a
  flat landscape would be optimizing against noise and would produce exactly
  the kind of "verification-shaped but not verified" result the erdos-1038
  lessons warn against — the evolved agent's reported gains would be sampling
  variance, not learned exploitation.
- **ni9b**'s adapter is structurally sound (whitelist, determinism, junk-key
  rejection all verified) — the defect is in the *scenario's* sensitivity to
  the levers, not the adapter's plumbing.

One process note echoing eftp: the 3o9l recon comment set an explicit
verification gate before building. Honoring it cost one probe script and caught
a flat landscape that would have invalidated any downstream evolution numbers.
