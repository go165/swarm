# AI Village → SWARM: mapping design

**Source:** [`aidigestorg/ai-village`](https://huggingface.co/datasets/aidigestorg/ai-village)
(AI Digest). Access granted 2026-09-21; figures below measured against the
export of 2026-09-20 (`manifest.json`), not the dataset card's prose, which is
roughly 2× stale. Tracked as bead `vu70`; the calibration question it feeds is
`fcmy.7`.

This is the design gate that has to clear before any bridge code is written. It
answers four questions — which regime, what counts as an interaction, what
stands in for task progress, and how the addressing heuristic gets validated —
and then raises a fifth that the first four expose and that nothing in the
dataset resolves.

## What the data actually is

| | pre-cutover | documented | undocumented |
|---|---|---|---|
| window | 2025-04-02 → 2026-03-24 | 2026-03-24 → 2026-07-03 | 2026-07-03 → 2026-09-20 |
| computer-use turns | 749,713 | 658,135 | 1,102,639 |
| sessions | 25,844 | 19,013 | 33,505 |
| consolidations | 0 | 18,854 | 33,471 |
| chat messages | 105,950 | 28,215 | 49,320 |
| distinct chat speakers | 24 | 23 | 32 |
| turn error rate | 5.36% | 7.26% | 5.92% |
| repeat-of-previous-action rate | 4.35% | 6.08% | 4.43% |

Totals: 2,510,487 turns, 381,610 events, 246,151 memories, 183,485 chat
messages, 78,362 sessions, 46 agents across the life of the village.

## D1 — Regime: post-cutover, primary window 2026-03-24 → 2026-07-03

`CHANGELOG.md` states that the 2026-03-24 perma-computer-use rollout is "the
single biggest structural change in the dataset" and that data either side
should be treated as different regimes. The event vocabulary bears that out —
it is close to disjoint:

| actionType | pre | post |
|---|---|---|
| `WAIT` | 36,022 | 0 |
| `PAUSE` | 635 | 39,837 |
| `CONSOLIDATE` | 0 | 52,325 |
| `START_USING_COMPUTER` | 25,839 | 136 |
| `STOP_USING_COMPUTER` | 25,809 | 130 |
| `OUTREACH_APPROVAL_*` | 0 | 695 |

**The reason to choose post-cutover is semantic uniformity, not stability.**
It is worth being exact about this, because the tempting claim is false. The
changelog lists 90 dated scaffolding changes: 63 before the cutover over 356
days (0.18/day) and 27 after over the 101 documented days (0.27/day). By
documented change density the chosen window is *churnier* than the one being
rejected. Some of that is likely recency bias in the changelog's own coverage,
which is an argument for distrusting both numbers rather than for preferring
either window.

What post-cutover actually buys is that every session means the same thing.
Agents are permanently in computer-use mode and consolidate every ~40 actions,
so the consolidation-bounded session is a uniform, mechanically-defined unit
(18,854 of them in the primary window). Pre-cutover, session boundaries are
agent-chosen, so "session" is itself a behavioural variable — it cannot serve
as a neutral observation unit.

Consequences to carry forward:

- Scaffolding-change dates are **known breakpoints**, not noise the window
  escapes. Fit sensitivity to them explicitly; do not assume the window is
  homogeneous just because it is inside one regime.
- The undocumented window holds 1.1M turns — more than the primary window. It
  is the densest part of the corpus and the least explicable, because the
  changelog stops at 2026-07-03 while data runs to 2026-09-20. **Hold it out
  as a replication set, do not discard it.** A fit that reproduces there is
  more convincing than one that cannot be checked; a fit that fails there is
  informative about scaffolding sensitivity.

## D2 — The interaction: session-anchored, chat-derived counterparty

`SoftInteraction` is dyadic: initiator × counterparty, with a joint outcome.
**The Village records no dyadic interactions.** Computer use is solo; chat is
broadcast into rooms. There is no pairwise unit with an outcome anywhere in the
schema, so the bridge must construct one. The construction proposed here:

- **Unit** — one consolidation-bounded session `S` of agent `A`.
- **Initiator** — `A`.
- **Counterparty** — derived from chat. Chat is reachable from the turn stream:
  `send_message_back_to_chat` is an `agent_action` (100,354 occurrences), so
  messages are actions *inside* sessions and join cleanly to `S`. Take the
  messages `A` sent during `S` that name exactly one other agent `B`; the modal
  `B` is the counterparty.
- **Observables** — `rework_count` from consecutive-identical `agent_action`
  within `S`; `verifier_rejections` from turns in `S` with non-null `error`;
  `counterparty_engagement_delta` from whether `B` replied naming `A` inside a
  window.

Both turn-level channels are externally generated and carry usable signal at
these rates (7.26% error, 6.08% repeat in the primary window), so neither is a
self-report.

**The trap to design against.** Most sessions will have no chat counterparty at
all. Dropping those sessions is a selection on sociability, and sociable
sessions are plausibly different in quality from heads-down ones. That selection
can manufacture exactly the effect `quality_gap` exists to detect — an apparent
adverse-selection signal that is an artifact of which sessions were kept.
Report the retained fraction, and compute the metrics on the dropped-vs-kept
split before reading anything into the headline number.

## D3 — Task progress: no admissible observable exists

This is the finding that most changes the plan. Every candidate fails:

| candidate | volume | why it fails |
|---|---|---|
| `summaries.jsonl` content | 939 | `SCHEMA.md`: generated **without** seeing inside computer-use sessions; "treat as secondary" |
| `STOP_USING_COMPUTER.summary` | 25,809 pre / 130 post | self-report, and absent from the chosen regime |
| `CONSOLIDATE.nextSessionGoal` | 52,325 | forward-looking intent, not retrospective progress; also self-report |
| `computer_use_sessions.has_been_asked_to_stop` | **1 in 78,362** | field is effectively dead |
| `USER_TALK` | 2,228 post | sparse and not attributable to a task |

The two survivors of the self-report objection (`STOP_USING_COMPUTER.summary`,
`CONSOLIDATE.nextSessionGoal`) fail it anyway, and they fail it in the specific
way that matters here. `fcmy.7` exists because `beta_swarm`'s deceptive
archetype inflates `task_progress_delta` to ~0.75 regardless of true quality,
making progress an actively misleading channel and engagement the discriminating
one — and the posterior recovered that, correctly and circularly. Feeding
agent self-reported progress in as `task_progress` would rebuild that same
circularity out of new parts. If engagement won again, we would have arranged
for it again.

**Decision: drop `task_progress` and fit three channels** (rework, verifier,
engagement), reporting plainly that the default 0.4-weight channel has no
admissible source in this corpus.

This cuts both ways and the writeup must say so. Removing progress removes the
built-in answer, which strengthens the test. But it also means the Village
**cannot** test the thing `fcmy.7` most wants tested — whether a fit correctly
*down*-weights a misleading progress channel — because there is no progress
channel to down-weight. The Village yields a partial answer to `fcmy.7`, over
three channels, not the complete one.

## D4 — Validating the naming → addressing heuristic

The counterparty construction rests on "names exactly one agent" standing in for
"addresses that agent". Measured on the main room (149,307 of 183,485 messages,
44 distinct speakers): 56.1% name at least one agent, and 50,987 name exactly
one. 26.7% contain an `@handle`.

Naming is not addressing — a message may discuss `B` rather than speak to it.
Before the heuristic is used:

1. Draw a stratified sample of n=200 messages naming exactly one agent, spread
   across the primary window.
2. Label each as *addresses* vs *mentions*. Report precision with a CI; adopt
   the heuristic only above a pre-registered bar (0.8 proposed), and record the
   bar before looking.
3. **Controls, both directions.** A positive control per pattern class, and a
   negative control of 100 messages naming zero agents confirming none are
   addressed. A vocabulary scan that reports a clean negative without controls
   has been wrong in this repo before.
4. Check whether `@handle` is the cleaner signal, and how far the two overlap.

Two mechanical traps, both already hit while measuring the numbers above:
display names are prefixes of each other (`Claude Opus 4` vs `Claude Opus 4.5`),
so match **longest-first**; and `\b` never matches before `@`, so a
word-boundary-anchored `@handle` pattern is silently dead.

## D5 — The unresolved problem: there is no outcome variable

The four decisions above define observables. They do not define `v`.

SWARM's proxy maps observables to `p = P(v = +1)`, and `fcmy.7`'s posterior fits
proxy parameters against *observed outcomes*. **The Village ships no outcome
labels, and nothing in the schema stands in for one.** Session summaries are
self-reports; engagement is already spent as an input channel and cannot also
serve as the target without circularity; human reaction (`USER_TALK`, 2,228 in
the primary window) is sparse and not attributable to a session.

This is load-bearing for what `vu70` can deliver, so it should be settled
deliberately rather than discovered halfway through the bridge:

- If a defensible `v` can be constructed — and the case for one has to be made
  explicitly, not assumed — `vu70` delivers the calibration it promised, over
  three channels.
- If it cannot, `vu70` downgrades from *refit the weights* to *descriptive
  validation*: the observable distributions, their correlation structure, and
  how the existing metrics behave on real multi-agent history. That is still
  worth having and still novel, but it is a smaller claim, and `fcmy.7` falls
  back to MiroShark as the not-authored-by-us generator.

Deciding D5 is the next step. It is a research question, not an implementation
detail, and no amount of bridge code answers it.

## Standing constraints

Licence is research-use-only: no training or fine-tuning of AI systems without
written permission, no re-identification, and citation of AI Digest / AI Village
in any resulting work. Everything above is parameter fitting and metric
computation, which is inside those terms. Any blog post, paper or docs page
built on this data carries the citation.

Upstream redaction to expect in text: `[REDACTED]` for credentials and
infrastructure, `[BLOB_REMOVED]` for thinking signatures, `[IMAGE_REMOVED]` for
embedded screenshots.
