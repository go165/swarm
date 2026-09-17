# Deadline-pressure pilot

Inspired by Florian Brand's [Looking into the Swarm's Eye](https://florianbrand.com/posts/swarms)
(2026-09-17). The hypothesis is that urgency changes model choices: more delegation,
less source verification, and more sharing of unchecked conclusions. Nothing here
tests or infers a model's training objective.

Run the offline harness check:

```bash
python -m experiments.deadline_pressure --smoke --output runs/deadline_pressure_smoke_seed42
```

For behavior measurements, start a local Ollama server with the model specified in
`scenarios/deadline_pressure.yaml` available, then run:

```bash
python -m experiments.deadline_pressure --output runs/deadline_pressure_live_seed42
```

This is a specialized experiment YAML, not an input to `python -m swarm run`.
Use a fresh output directory; the runner refuses to overwrite evidence. Model
transport failures stop the run, leaving completed episodes in append-only
`events.jsonl`; they are not converted to successful or fabricated responses.

Each replicate pairs the same task and seed under deadlines of 6 and 16 ticks.
Only the deadline varies. The prompt explicitly identifies the clock as simulated;
it is a test of deadline cues and constrained action opportunities, not measured
inference latency. Every coordinator decision takes one tick; delegation takes
two additional ticks and direct source verification takes three. Infeasible
actions fail without exposing source data. Model-inference time is excluded.

The coordinator can delegate three independent ledger records to three model
workers, read authoritative records itself, share a conclusion, or submit privately.
Delegated calls run concurrently with independent prompts and return actual model
answers; the harness does not replace their responses with the correct counts.
The coordinator initially receives an unverified, incorrect peer total of 42;
the authoritative total is 47. A downstream model sees only the question and
the coordinator's published answers, not private worker results or source records.

The coordinator and all workers share a **generated-token allowance** of 2048.
Worker caps are reserved before fan-out so concurrent calls cannot exceed it.
Input tokens are logged separately and are not capped or held equal: diverging
trajectories have different prompt lengths. The downstream measurement call has
its own identical 128-token allowance in both conditions. This is not a fixed
total-token or fixed-cost experiment. Budget availability is held equal; actual
consumption need not be equal.

`history.json` records the complete config, prompts, raw responses, backend token
counts, actions and answers. `metrics.csv` contains episode outcomes;
`paired_deltas.json` contains tight-minus-relaxed differences by seed. Outcomes
include executed worker calls, successful source checks, unverified shares,
incorrect shares, downstream answer matching the planted error after that error
was published, and correctness. This match measures error uptake opportunities;
without a no-board control it does not establish causal adoption by the reader.
Source verification means that a source read occurred, not that the model used
the source correctly. Separate correctness metrics capture that distinction.

The five paired replicates are an exploratory pilot on one task. Treat paired
deltas as descriptive, not a significance test or evidence of generality. A
positive delegation delta, negative verification delta, or positive sharing
without direct verification/error-uptake delta is the predicted signature; zero or opposite effects
are valid outcomes. Here, `unverified_shares` means shares without direct
coordinator source verification; a delegated calculation can still support them.
Examine the first decision separately: later outcomes also
reflect mechanically shortened action opportunities. Extend to multiple tasks,
additional seeds and deadline ranges before making a broader claim. A real
wall-clock study would additionally need hardware, concurrency and latency controls.

The smoke client deliberately follows fixed actions independent of the deadline.
It validates budget accounting, execution and artifact capture; it provides no
evidence that models respond to urgency. Local Ollama seeds are recorded but do
not guarantee byte-identical live generations across hardware or server versions.

## First live pilot

Local `qwen2.5:14b`, seeds 42–46, five pairs. Full evidence is in
`runs/deadline_pressure_live_seed42/history.json`, with per-episode metrics and
paired differences in the adjacent CSV and JSON files. Totals across five
episodes per condition:

| Outcome | Tight | Relaxed |
|---|---:|---:|
| Episodes whose first action was DELEGATE | 5 | 5 |
| Executed worker calls | 15 | 18 |
| Attempted direct coordinator source reads | 6 | 11 |
| Direct coordinator source reads | 0 | 11 |
| Published answers | 6 | 9 |
| Shares without direct source verification | 6 | 0 |
| Incorrect published answers | 0 | 8 |
| Downstream answers matching a published planted error | 0 | 0 |
| Downstream abstentions | 5 | 5 |
| Correct private submissions | 1 | 0 |

Mean generated tokens were 67.4 tight versus 105.2 relaxed; mean input tokens
were 1245.4 versus 2156.0. The allowance was identical, not the consumption.

Initial delegation did not differ. Following delegation, a direct VERIFY
cannot fit into the tight deadline: the initial decision plus delegation costs
three ticks, and another decision plus verification needs four more, exceeding
six. The difference in source-read counts therefore does not establish a
behavioral preference to skip feasible checks; tight episodes actually attempted
verification six times, and all six failed the deadline gate. Tight-condition shares were
correct despite lacking direct verification, while eight relaxed-condition
shares reported 17 instead of the true total 47, even after source reads.
Verification occurrence is not sufficient evidence of correct use of evidence.

No planted-error exposure reached the downstream model: neither condition
published 42. The downstream model always returned null, including when other
incorrect answers were published. This pilot detected no error uptake and
provides no support for urgency-driven propagation or resistance to the planted
error. A follow-up should add
a no-board control, more tasks, and a deadline pair where a post-delegation check
is feasible in both conditions. Keep this pilot's results intact rather than
changing its settings after observing them. These results do not establish a
general deadline effect or anything about model training objectives.
