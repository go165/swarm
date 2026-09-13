"""The planted defects: one exact text substitution each, applied to reference.py.

Every defect is unambiguous: ``tests/test_verifier_recall_fixture.py`` runs a
probe that the reference passes and the planted module fails. Ids are stable,
so a scored run stays comparable if defects are added later.
"""

from __future__ import annotations

from typing import List, NamedTuple


class Defect(NamedTuple):
    id: str
    function: str
    category: str
    old: str
    new: str
    description: str


DEFECTS: List[Defect] = [
    Defect(
        "D01", "deposit", "wrong-bound",
        "    if amount <= 0:\n        raise ValueError(\"deposit must be positive\")",
        "    if amount < 0:\n        raise ValueError(\"deposit must be positive\")",
        "A zero deposit is accepted and logged as a history entry.",
    ),
    Defect(
        "D02", "withdraw", "missing-check",
        "    if agent_id in ledger.frozen:\n        raise PermissionError(f\"{agent_id} is frozen\")\n",
        "",
        "Frozen agents can withdraw; the freeze check was removed.",
    ),
    Defect(
        "D03", "withdraw", "wrong-bound",
        "    if amount > balance:",
        "    if amount > balance + 1.0:",
        "Overdrafts of up to 1.0 are allowed.",
    ),
    Defect(
        "D04", "transfer", "ordering",
        "    withdraw(ledger, src, amount, epoch)\n    deposit(ledger, dst, amount, epoch)",
        "    deposit(ledger, dst, amount, epoch)\n    withdraw(ledger, src, amount, epoch)",
        "Credits dst before debiting src, so a failed withdraw leaves dst credited.",
    ),
    Defect(
        "D05", "apply_tax", "wrong-bound",
        "    if not 0.0 <= rate <= 1.0:",
        "    if not 0.0 <= rate <= 100.0:",
        "Rates above 1 are accepted, so tax can exceed the amount.",
    ),
    Defect(
        "D06", "epoch_entries", "off-by-one",
        "if start <= e.epoch < end]",
        "if start <= e.epoch <= end]",
        "The window includes epoch == end, contradicting the half-open docstring.",
    ),
    Defect(
        "D07", "last_n_amounts", "off-by-one",
        "    return amounts[-n:] if n > 0 else []",
        "    return amounts[-n - 1:] if n > 0 else []",
        "Returns n + 1 amounts.",
    ),
    Defect(
        "D08", "mean_balance", "missing-check",
        "    if not ledger.balances:\n        return 0.0\n",
        "",
        "An empty ledger raises ZeroDivisionError instead of returning 0.0.",
    ),
    Defect(
        "D09", "memo_prefix", "missing-none-check",
        "    if entry.memo is None:\n        return \"\"\n",
        "",
        "An entry without a memo raises TypeError.",
    ),
    Defect(
        "D10", "top_holders", "wrong-sort",
        "key=lambda kv: (-kv[1], kv[0])",
        "key=lambda kv: (kv[1], kv[0])",
        "Sorts smallest balances first, so it returns the bottom k.",
    ),
    Defect(
        "D11", "freeze_if_overdrawn", "sign-error",
        "        if balance < -limit and agent not in ledger.frozen:",
        "        if balance < limit and agent not in ledger.frozen:",
        "Freezes every agent below +limit, including solvent ones.",
    ),
    Defect(
        "D12", "merge_ledgers", "aliasing",
        "    merged = Ledger(balances=dict(a.balances), history=list(a.history), frozen=set(a.frozen))",
        "    merged = Ledger(balances=a.balances, history=a.history, frozen=a.frozen)",
        "Merging mutates ledger a through shared dict/list/set references.",
    ),
]
