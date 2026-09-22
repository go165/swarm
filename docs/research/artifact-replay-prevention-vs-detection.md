# Artifact replay: prevention vs detection (bead `iujo`)

**Status:** pre-registered 2026-09-13, before any run. The prediction and pinned
lever parameters below were committed on their own, ahead of the implementation
and the sweep; results are appended underneath without editing this section.

## Question

A receipt, or any artifact that carries quality, holds a quality signal earned in
one interaction. If another agent can present it in a different interaction, the
accept decision conditions on a `p` that belongs to someone else. Provenance and
quality come apart, and `quality_gap = E[p | accepted] − E[p | rejected]` should
fall without any agent misreporting its own behaviour. This is the artifact-level
sibling of the agent-level `information_laundering` attack, and the simulation
analogue of the cross-model reasoning-blob downgrade in arXiv:2608.09867.

The memetic-spread study (bead `kgxc`, 2026-08-08) found detection dominating
prevention-by-reset, at a ~12% welfare tax. There, prevention was destructive:
resetting memory threw away good state along with bad. Here prevention is cheap
and mechanical: a receipt is only honoured when its presenter is its producer.
Does the ordering invert?

## Mechanism

- **Receipts.** Each accepted interaction publishes a receipt artifact owned by
  the initiator and stamped with that interaction's `p`
  (`artifact_receipts_enabled`).
- **Counterparties** (honest agents with `trust_artifacts: true`) accept on
  `max(trust, receipt p)`. The receipt is the one the proposal presents, or
  else the initiator's own best visible receipt.
- **Replayer** (`artifact_replayer`): an adversarial agent whose own work draws
  low-quality observables. It presents the highest-`p` receipt it can see from
  another producer.
- **Prevention lever** (`artifact_context_binding_enabled`): before the accept
  decision, a presented receipt whose producer is not the presenter is
  stripped. Costs nothing and penalizes no one.
- **Detection lever** (`artifact_replay_detection_enabled`): after the accept
  decision, a replayed presentation is caught with probability `rate`. The
  initiator pays `penalty` and loses `penalty` reputation. Any other accepted
  interaction is falsely flagged with probability `false_positive_rate` for the
  same penalty.

## Arms (one lever at a time)

| arm | replayer replays | binding | detection |
|---|---|---|---|
| `control` | no (presents nothing) | off | off |
| `replay` | yes | off | off |
| `binding` | yes | **on** | off |
| `detection` | yes | off | **on** |

Pinned detection parameters: `rate = 0.5`, `false_positive_rate = 0.05`,
`penalty = 1.0`. Seeds 42–51 (10 per arm). The scenario may be calibrated
**only** on the `control` and `replay` arms, so the rejected pool is non-empty
and `quality_gap` is not degenerate. Lever parameters do not change after this
commit.

## Predictions

1. **Replay is adverse selection.** Mean `quality_gap` is lower in `replay` than
   in `control`.
2. **Prevention dominates detection (inversion of `kgxc`).** `binding` recovers
   more of the gap than `detection`: mean `quality_gap(binding) >
   quality_gap(detection)`. It also costs less: mean `total_welfare(binding) ≥
   total_welfare(detection)`.

**Falsifiers.** Prediction 1 fails if `replay` does not lower the gap. The
harness then has no replay effect and prediction 2 is moot. Prediction 2 fails
if detection matches or beats binding on the gap, or has higher welfare. Either
outcome is recorded below as observed.

---

## Results (2026-09-13, 10 seeds per arm)

Run: `python scripts/sweep_artifact_replay.py --seeds 10 --out experiments/artifact_replay/results/2026-09-13`.
Scenario: `scenarios/artifact_replay.yaml`.
Per-run rows are in `sweep.csv`, means and SDs in `summary.json`.

**Calibration disclosed.** The pre-registration allowed tuning on `control` and
`replay` only. Two changes were made, both before any lever arm ran. Honest
`acceptance_threshold` went from 0.7 to 0.6: at 0.7 honest agents accepted no
proposal at all, replayed or not, so replay could not change any outcome. A third, never-replaying low-quality
agent was added: with only replayers, every proposal in the `replay` arm was
accepted, and `quality_gap` read exactly 0.0 because the rejected pool was
empty. Lever parameters are as pinned.

| arm | quality_gap | toxicity | total welfare | accepted | replays accepted / presented |
|---|---|---|---|---|---|
| control | 0.1815 ± 0.0169 | 0.4071 ± 0.0159 | 158.6 ± 7.2 | 270.6 | 0 / 0 |
| replay | **0.0946** ± 0.0204 | 0.4805 ± 0.0058 | 158.4 ± 7.9 | 432.3 | 241.8 / 242.2 |
| binding | **0.1815** ± 0.0169 | 0.4071 ± 0.0159 | 158.6 ± 7.2 | 270.6 | 0 / 0 (242.2 blocked) |
| detection | 0.1015 ± 0.0119 | 0.4825 ± 0.0039 | **22.6** ± 11.3 | 425.0 | 241.8 / 242.2 (119.7 caught, 11.0 false positives) |

**Prediction 1 holds.** Replay cuts `quality_gap` by 0.087, about four control
SDs, and raises toxicity from 0.407 to 0.481. Accepted interactions rise from
270.6 to 432.3, and replayed presentations are accepted 241.8 times out of 242.2.

**Prediction 2 holds.** Binding restores the gap fully (0.1815, identical to
control, run for run), while detection leaves it at 0.1015. Binding costs no
welfare. Detection's welfare is 22.6 against binding's 158.6. The
memetic-spread ordering inverts.

### What the result does and does not show

- **Binding's win is by construction.** Presenter identity cannot be forged in
  this model and the check is free, so binding stripping 100% of replays is
  guaranteed. Its arm reproducing control exactly is expected: a stripped
  replayer falls back to its own receipts, as in control. The informative half
  of prediction 2 is detection's failure, not binding's success.
- **Detection never changes who is accepted.** Counterparties take a presented
  receipt at face value (`max(trust, receipt p)`), so the reputation penalty on
  a caught replayer never feeds back into acceptance. Replays are accepted at
  the same rate as with no lever (241.8 of 242.2). Detection here punishes;
  it does not select. A detector whose flags reached counterparty trust, or
  froze the replayer, could recover part of the gap. This result is about
  post-hoc penalties against a non-adaptive replayer, not about detection in
  general.
- **Most of detection's welfare loss is the penalty itself.** 119.7 caught
  plus 11.0 false positives at penalty 1.0 is ~131 of the ~136 drop. Welfare
  counts penalties as social cost. Only the ~11 false-positive penalties land
  on non-replaying agents.
- **`quality_gap` has degenerate epochs** (0.0 when nothing is rejected):
  2.7 of 20 per run in `replay` and 1.1 in `detection`, none in `control` or
  `binding`. They pull those arms' mean gap toward 0 and slightly overstate
  the drop. Toxicity, which is not degenerate, moves the same way.

**Next** (`vwj3`): whether the capability precondition behind binding survives
decomposition, e.g. a replayer that relays through an accomplice whose identity
matches the receipt.
