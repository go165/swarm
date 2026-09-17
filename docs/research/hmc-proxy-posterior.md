# Posterior inference over proxy parameters: HMC vs. the evidence_scale grid

**Status:** prototype complete, result positive, adoption not yet decided.
**Beads:** `distributional-agi-safety-fcmy` (epic), `.1`–`.4`.
**Code:** now in [`swarm-ai-research/beta-swarm`](https://github.com/swarm-ai-research/beta-swarm)
(vendored here as the `beta-swarm/` submodule) — `beta_swarm/inference/`,
`scripts/hmc_vs_grid_evidence_scale.py`, `tests/test_hmc.py`. Paths in this note are
relative to that repo's root. It was written while `beta_swarm/` still lived in this
repo, at commit `5ab1a982`; the split-out is `beta-swarm` commit `8005468`.
**Runs:** `runs/20260916T2025*_hmc_vs_grid_seed{0,1,2}/`.
**Reference:** Betancourt, *A Conceptual Introduction to Hamiltonian Monte Carlo*, arXiv:1701.02434.

## The question

`beta_swarm/proxy.py` maps observables to a Beta belief through seven hand-set
constants. One of them, `evidence_scale`, is fit — by a 1-D grid sweep
(`sweep_evidence_scale`) that reports a point estimate. The other six are
never fit at all.

Because the outcome `v` is continuous on `[0, 1]`, the proxy already *defines a
likelihood*:

```
w      = softmax([z1, z2, z3, 0])      # weights on the simplex
v_hat  = w . x                         # x in [-1,1]^4, from observables
mean   = sigmoid(k * v_hat)
conc   = c0 + s * e
v     ~ Beta(mean * conc, (1 - mean) * conc)
```

The calibration harness scores this predictive distribution (CRPS and PIT are
proper scoring rules for exactly it) but never inverts it. So: is the 1-D grid
leaving anything on the table?

## Method

Six unconstrained parameters `(z1, z2, z3, log_k, log_c0, log_s)`, weakly
informative Normal priors placed directly on those coordinates (so no Jacobian
adjustment; a Normal on `log_k` is a log-normal on `k`, which is what a positive
scale parameter wants anyway).

Sampled with a hand-rolled dynamic HMC — no new dependencies, deliberately: the
question is whether a probabilistic-programming stack is worth adopting, and
adopting one to answer it would prejudge it. Following Betancourt, the sampler
has dynamic trajectory lengths with a U-turn criterion (not a static length),
multinomial sampling from the trajectory, dual-averaging step-size adaptation to
a target accept of 0.8, a diagonal inverse metric from windowed warmup, and
divergence / E-BFMI / split-R-hat / ESS diagnostics.

The gradient is analytic, hand-derived. That is the highest-risk part of the
whole exercise — a subtly wrong gradient yields a smooth, plausible posterior
centred on the wrong place, and nothing downstream would catch it — so it is
checked against central finite differences at five random points, and the
likelihood is checked against `scipy.stats.beta.logpdf` evaluated through the
production proxy.

**Data generation is misspecified on purpose.** Outcomes come from the archetype
emission models in `beta_swarm/agents.py` (honest / mediocre / deceptive), not
from the proxy's own Beta. That is the real operating condition and a harder
test than self-recovery.

n = 3000, 4 chains × 1000 draws after 1000 warmup, seeds 0/1/2.

## Results

Diagnostics were clean on every run: **0 divergences, 0 max-depth hits, R-hat ≤
1.0012, min ESS 4000, E-BFMI ≈ 1.1–1.2.** The sampler itself is not the story;
that it reports cleanly here matters only because the test suite shows it
reports *dirty* when it should (Neal's funnel produces divergences; two
separated modes produce R-hat > 1.01).

### 1. The parameters are strongly correlated — the grid cannot reach the joint optimum

`log_c0` ↔ `log_s` (`base_concentration` ↔ `evidence_scale`): **r = −0.77,
−0.76, −0.76** across the three seeds.

This is the structural argument, and it needs no appeal to taste. The grid moves
`evidence_scale` with `base_concentration` frozen at its hand-set 2.0. When the
two trade off this strongly, the best `evidence_scale` *conditional on
`c0 = 2.0`* is not the best `evidence_scale`, and no amount of refining the 1-D
grid fixes that. It is a limitation of the search shape, not its resolution.

### 2. The hand-set weights are badly wrong for this generative model

| parameter | hand-set default | posterior median (90% CI, seed 0) |
|---|---|---|
| `w_progress` | 0.40 | 0.002 (0.001, 0.005) |
| `w_rework` | 0.20 | ~0.002 |
| `w_verifier` | 0.20 | ~0.002 |
| `w_engagement` | 0.20 | **0.994 (0.991, 0.997)** |
| `sigmoid_k` | 2.0 | 1.385 (1.321, 1.445) |
| `base_concentration` | 2.0 | 0.968 (0.767, 1.171) |
| `evidence_scale` | 1.5 | 3.161 (2.915, 3.411) |

The posterior puts essentially all weight on counterparty engagement and
approximately none on task progress. Stable to three decimal places across
seeds.

This is interpretable, and the interpretation is the caveat. In `agents.py`,
deceptive agents emit inflated `task_progress_delta` (≈0.75 regardless of true
quality) while their engagement stays low, because engagement is the one channel
a lone deceiver cannot manufacture. Progress is therefore an actively
*misleading* signal in this population and engagement is the discriminating one.
The posterior found that. It is recovering a property of the simulator, which
is by construction — not a discovered fact about real agent systems.

What generalizes is the *method*: this is weight misspecification that the 1-D
grid could not have surfaced, because it never varies the weights.

### 3. Calibration is roughly twice as good at the posterior mean

| | PIT deviation | tail ECE | CRPS | sharpness |
|---|---|---|---|---|
| posterior mean | **0.235** | **0.180** | **0.116** | 5.28 |
| grid (sharpest-calibrated) | 0.370 | 0.308 | 0.221 | 10.22 |

The grid's pick is worse on PIT deviation — *its own selection criterion* — by
57%. It is sharper, having bought that sharpness with calibration it could not
afford. Note that the grid's best-PIT pick (seed 0, n=3000: scale 5.0, PIT
0.333) is still worse than the posterior mean, so this is not an artifact of the
selection rule used here.

Also note the comparison is not strictly apples-to-apples: the grid selects on
PIT, HMC targets the posterior. Both derive from proper scoring rules, but the
honest reading is "the posterior lands somewhere better on the grid's own
metric", not "HMC optimizes PIT better".

### 4. The governance-lever argument did **not** hold up

The bead predicted that parameter uncertainty would put a credible interval on
`tail_mass(tau)` wide enough to change a call the point estimate makes
confidently. It does not, at this sample size:

- 90% CI width on `P(v < 0.4)`: **median 0.011, max 0.038**
- interactions whose CI straddles the 0.5 line: **4 of 400**
- cases where the point estimate reads confident but the posterior does not: **0**

Parameter uncertainty is real but small relative to the decision margin. The
uncertainty does concentrate on borderline cases (spread correlates negatively
with distance from the threshold — pinned by a test), which is the right shape;
there is just not much of it.

Two caveats pointing opposite ways. At n = 3000 the posterior is tight almost by
construction, so this says little about small-sample regimes. Conversely, the
model is misspecified, and credible intervals under misspecification are known
to be too narrow — the honest statement is that the tail-mass intervals reported
here are a *lower bound* on the real uncertainty, and a sandwich-corrected or
cross-validated interval would be the way to check.

## Relation to Arm A Finding 4

`docs/research/calibration-arm-a-deviation-analysis.md` argues that latent
`p_true` is unrecoverable in principle: observables carry information about `v`
only, so no estimator can distinguish an interaction drawn with `p_true = 0.4`
from one drawn with `p_true = 0.2` given the same realized `v`.

That argument stands and is not contradicted here, because it is about a
different target. Finding 4 concerns recovering a **per-interaction latent** from
a **single realized outcome** — a fundamentally under-determined problem.
This work estimates **global parameters** shared across N interactions, which
pools information and is well-posed; the parameter-recovery test confirms the
posterior covers known truth. A reader who knows Finding 4 should not read this
as overturning it, and nothing here licenses per-interaction `p_true` recovery.

## Verdict

**Two of the three adoption criteria are met** (correlation structure a per-axis
grid cannot reach; weight misspecification it cannot surface). The third — a
governance call that changes — is not.

That is enough to justify fitting the proxy rather than hand-setting it, but
*not* on the strength of the governance-uncertainty argument, which should be
dropped from the case until a small-sample or misspecification-corrected version
of check 4 is run.

Open before adoption (bead `.4`):

1. Re-run at n = 100–500, where the tail-mass intervals should actually bite.
2. Cross-validate or sandwich-correct the intervals, given known misspecification.
3. If adopted, replace the hand-rolled sampler with numpyro or blackjax. It was
   written to avoid a dependency during evaluation, not to be maintained. The
   cost of that swap is a jax dependency in a repo that has deliberately stayed
   on numpy/scipy/sklearn, and that tradeoff deserves its own decision.
4. The `w_engagement ≈ 0.99` result must be reproduced against a generative
   model that was not written by us before it informs any change to the proxy's
   defaults. Right now it is a statement about `agents.py`.

## Addendum, 2026-09-17: the code moved

`beta_swarm` was split out of this repo into
[`swarm-ai-research/beta-swarm`](https://github.com/swarm-ai-research/beta-swarm)
and vendored back as the `beta-swarm/` submodule.

Worth recording because it nearly cost work. `beta_swarm/` had originally been
folded *in* from a standalone repo (`8e2a3984`), and both copies then kept
moving: this repo gained the PR-review fixes and the whole HMC package, while the
standalone gained a `ContainmentEscaper` adversary that never landed here. Ten of
fourteen shared files differed and **neither side was a superset**. Wiring the
submodule first would have deleted the HMC work from the working tree, since a
submodule replaces the directory with a checkout of the remote.

The order that worked: port the missing half into this repo (`98557793`), making
it the superset; then sync outward and push (`beta-swarm` `8005468`); only then
replace the directory with the submodule. The 161 tests pass identically on both
sides, which is what confirms nothing was dropped in either direction.
