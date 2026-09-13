"""Score review-stage and verify-stage findings against the answer key.

A finding is ``{"line": int, "summary": str}`` (``file`` is optional; only
planted.py is under review). Findings match defects one-to-one: each defect
takes the nearest unmatched finding within ``WINDOW`` lines. Unmatched findings
are false positives.

The quantity bead daxc asks for is the dropped-true-positive rate:

    dropped = |defects matched after review but not after verify|
              / |defects matched after review|

    python -m experiments.verifier_recall.score runs/<run>/workflow_output.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

HERE = Path(__file__).resolve().parent
WINDOW = 3


def load_key(path: Path = HERE / "answer_key.json") -> List[Dict]:
    return list(json.loads(path.read_text()))


def match(key: Sequence[Dict], findings: Sequence[Dict], window: int = WINDOW) -> Dict[str, int]:
    """Map defect id -> index of the finding that caught it."""
    taken: Set[int] = set()
    caught: Dict[str, int] = {}
    pairs = sorted(
        (abs(int(f["line"]) - d["line"]), d["id"], i)
        for d in key
        for i, f in enumerate(findings)
        if abs(int(f["line"]) - d["line"]) <= window
    )
    for _, defect_id, i in pairs:
        if defect_id in caught or i in taken:
            continue
        caught[defect_id] = i
        taken.add(i)
    return caught


def stage_metrics(key: Sequence[Dict], findings: Sequence[Dict]) -> Dict:
    caught = match(key, findings)
    n = len(findings)
    return {
        "n_findings": n,
        "true_positives": len(caught),
        "recall": len(caught) / len(key) if key else 0.0,
        "precision": len(caught) / n if n else None,
        "caught": sorted(caught),
    }


def score(key: Sequence[Dict], review: Sequence[Dict], verified: Sequence[Dict]) -> Dict:
    r = stage_metrics(key, review)
    v = stage_metrics(key, verified)
    dropped = sorted(set(r["caught"]) - set(v["caught"]))
    rate: Optional[float] = len(dropped) / len(r["caught"]) if r["caught"] else None
    return {
        "n_defects": len(key),
        "review": r,
        "verify": v,
        "dropped_true_positives": dropped,
        "dropped_true_positive_rate": rate,
        # A verifier can only remove findings, so anything caught only after
        # verification means the stages were not run on the same findings.
        "caught_only_after_verify": sorted(set(v["caught"]) - set(r["caught"])),
    }


# The three aggregation rules from hyperspace-two-swarms-lessons.md, as a
# minimum count of "not refuted" votes a finding needs to survive. A verifier
# that returned no verdict for a finding counts as refuting it, matching the
# "refute if uncertain" instruction.
RULES = {
    "any_drop": lambda n: n,          # every verifier must keep it
    "majority": lambda n: n // 2 + 1,
    "any_keeps": lambda n: 1,         # dropped only if all verifiers refute
}


def aggregate(findings: Sequence[Dict], verdicts: Sequence[Optional[Sequence[Dict]]], rule: str) -> List[Dict]:
    """Findings surviving verification under ``rule``; each needs a ``fid``."""
    panels = [{v["fid"]: v for v in vs} for vs in verdicts if vs is not None]
    need = RULES[rule](len(panels))
    return [
        f for f in findings
        if sum(1 for p in panels if f["fid"] in p and not p[f["fid"]]["refuted"]) >= need
    ]


def score_run(key: Sequence[Dict], findings: Sequence[Dict], verdicts: Sequence[Optional[Sequence[Dict]]]) -> Dict:
    """Score one review+verify run under every aggregation rule."""
    return {
        "n_verifiers": sum(1 for vs in verdicts if vs is not None),
        "rules": {rule: score(key, findings, aggregate(findings, verdicts, rule)) for rule in RULES},
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run", type=Path, help="workflow output: {unique: [...], verifiers: [[...], ...]}")
    opts = ap.parse_args(argv)
    run = json.loads(opts.run.read_text())
    print(json.dumps(score_run(load_key(), run["unique"], run["verifiers"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
