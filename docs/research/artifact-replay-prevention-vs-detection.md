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
