#!/usr/bin/env python3
"""Artifact replay sweep: control / replay / binding / detection (bead iujo).

One lever at a time on scenarios/artifact_replay.yaml, 10 seeds per arm from
base 42, as pre-registered in
docs/research/artifact-replay-prevention-vs-detection.md.

Usage:
    python scripts/sweep_artifact_replay.py                 # 10 seeds
    python scripts/sweep_artifact_replay.py --seeds 2       # quick
    python scripts/sweep_artifact_replay.py --out DIR
"""

import argparse
import copy
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from swarm.analysis.sweep import _extract_results  # noqa: E402
from swarm.governance.artifact_replay import (  # noqa: E402
    BLOCKED_KEY,
    PRESENTED_KEY,
    ArtifactReplayDetectorLever,
)
from swarm.scenarios import build_orchestrator, load_scenario  # noqa: E402

SCENARIO_PATH = PROJECT_ROOT / "scenarios" / "artifact_replay.yaml"
SEED_BASE = 42


def _set_replay(scenario: Any, on: bool) -> None:
    # Only the replaying spec(s) flip; the never-replaying agent keeps a
    # rejected pool in every arm.
    for spec in scenario.agent_specs:
        if spec["type"] == "artifact_replayer" and spec.get("config", {}).get("replay", True):
            spec["config"]["replay"] = on


def _gov(scenario: Any, **fields: Any) -> None:
    gc = scenario.orchestrator_config.governance_config
    for k, v in fields.items():
        setattr(gc, k, v)


ARMS: Dict[str, Callable[[Any], None]] = {
    "control": lambda s: _set_replay(s, False),
    "replay": lambda s: None,
    "binding": lambda s: _gov(s, artifact_context_binding_enabled=True),
    "detection": lambda s: _gov(s, artifact_replay_detection_enabled=True),
}


def run_one(base: Any, arm: str, seed: int) -> Dict[str, Any]:
    s = copy.deepcopy(base)
    ARMS[arm](s)
    s.orchestrator_config.seed = seed
    orch = build_orchestrator(s)
    tally = {"replay_presented": 0, "replay_accepted": 0, "presentations_blocked": 0}

    def count(interaction: Any, *_: Any) -> None:
        meta = interaction.metadata or {}
        if meta.get(BLOCKED_KEY):
            tally["presentations_blocked"] += 1
        if meta.get(PRESENTED_KEY) and interaction.initiator.startswith("artifact_replayer"):
            tally["replay_presented"] += 1
            tally["replay_accepted"] += int(bool(interaction.accepted))

    orch.on_interaction_complete(count)
    orch.run()
    result = _extract_results(orch, {"arm": arm}, 0, seed).to_dict()
    history = orch.get_metrics_history()
    detector = next(
        (lv for lv in orch.governance_engine._levers if isinstance(lv, ArtifactReplayDetectorLever)),
        None,
    ) if orch.governance_engine is not None else None
    row = {
        "arm": arm,
        "seed": seed,
        "avg_quality_gap": result["avg_quality_gap"],
        "avg_toxicity": result["avg_toxicity"],
        "total_welfare": result["total_welfare"],
        "total_interactions": result["total_interactions"],
        "accepted_interactions": result["accepted_interactions"],
        "degenerate_gap_epochs": sum(1 for m in history if m.quality_gap == 0.0),
        "caught_replays": detector.caught_replays if detector else 0,
        "false_positives": detector.false_positives if detector else 0,
        **tally,
    }
    return row


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--out", type=Path, default=None)
    opts = ap.parse_args(argv)

    base = load_scenario(SCENARIO_PATH)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = opts.out or PROJECT_ROOT / "runs" / f"{stamp}_artifact_replay_sweep"
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for arm in ARMS:
        for offset in range(opts.seeds):
            rows.append(run_one(base, arm, SEED_BASE + offset))
            print(f"{arm:9s} seed={rows[-1]['seed']} gap={rows[-1]['avg_quality_gap']:+.4f} "
                  f"welfare={rows[-1]['total_welfare']:.1f}", flush=True)

    with open(out / "sweep.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary: Dict[str, Any] = {"scenario": str(SCENARIO_PATH.relative_to(PROJECT_ROOT)),
                               "seeds": [SEED_BASE + i for i in range(opts.seeds)], "arms": {}}
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        cell: Dict[str, Any] = {}
        for key in ("avg_quality_gap", "avg_toxicity", "total_welfare", "accepted_interactions",
                    "replay_presented", "replay_accepted", "presentations_blocked",
                    "caught_replays", "false_positives", "degenerate_gap_epochs"):
            vals = [float(r[key]) for r in arm_rows]
            cell[key] = {"mean": statistics.mean(vals),
                         "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0}
        summary["arms"][arm] = cell
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n{'arm':10s} {'gap':>16s} {'toxicity':>16s} {'welfare':>18s} {'replay acc/pres':>16s}")
    for arm, c in summary["arms"].items():
        print(f"{arm:10s} {c['avg_quality_gap']['mean']:+.4f} ±{c['avg_quality_gap']['sd']:.4f} "
              f"{c['avg_toxicity']['mean']:.4f} ±{c['avg_toxicity']['sd']:.4f} "
              f"{c['total_welfare']['mean']:9.1f} ±{c['total_welfare']['sd']:6.1f} "
              f"{c['replay_accepted']['mean']:7.1f}/{c['replay_presented']['mean']:.1f}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
