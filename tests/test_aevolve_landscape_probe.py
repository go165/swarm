"""Guards for the A-Evolve fitness-landscape probe (beads-2qgp / 3o9l recon).

The probe is the reproducible evidence that the evolution benchmark has no
usable gradient over adversary knobs. These tests pin two things:

1. The control invariant — the harness DOES move on agent type/count — must
   always hold; if it breaks, the probe itself is measuring nothing.
2. Adversary knobs move toxicity. This was a strict xfail until 2qgp found
   the adversary laid low on every turn; it now guards against that
   regression.
"""

import pytest

from experiments.aevolve_landscape_probe import (
    FLAT_EPS,
    probe_attacker,
    spread,
)


@pytest.fixture(scope="module")
def attacker_rows():
    # 3 seeds keeps the test cheap; the flat/gradient gap is not seed-sensitive.
    return probe_attacker(n_seeds=3)


def test_probe_produces_all_phenotypes(attacker_rows):
    names = {r["phenotype"] for r in attacker_rows}
    assert {"passive", "aggressive", "stealth"} <= names
    assert {"mix:0_deceptive", "mix:4_deceptive"} <= names


def test_mix_control_has_gradient(attacker_rows):
    """The load-bearing control: toxicity must move with agent mix, else the
    probe is measuring a dead harness rather than a flat knob landscape."""
    mix = [r for r in attacker_rows if r["phenotype"].startswith("mix:")]
    assert spread(mix, "toxicity") > 0.05


def test_attacker_knobs_have_gradient(attacker_rows):
    knobs = [r for r in attacker_rows if not r["phenotype"].startswith("mix:")]
    assert spread(knobs, "toxicity") > FLAT_EPS
