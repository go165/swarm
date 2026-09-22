"""Reference (defect-free) escrow ledger for the verifier-recall fixture.

This is the *base* side of the review diff. ``build_fixture.py`` applies the
planted defects in ``defects.py`` to produce ``planted.py``, the head side a
review workflow is pointed at. Nothing imports this module at runtime; it
exists so each planted defect has a correct counterpart that tests can run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Entry:
    agent_id: str
    amount: float
    epoch: int
    memo: Optional[str] = None


@dataclass
class Ledger:
    balances: Dict[str, float] = field(default_factory=dict)
    history: List[Entry] = field(default_factory=list)
    frozen: set = field(default_factory=set)


def deposit(ledger: Ledger, agent_id: str, amount: float, epoch: int) -> None:
    """Credit a positive amount to an agent."""
    if amount <= 0:
        raise ValueError("deposit must be positive")
    ledger.balances[agent_id] = ledger.balances.get(agent_id, 0.0) + amount
    ledger.history.append(Entry(agent_id, amount, epoch))


def withdraw(ledger: Ledger, agent_id: str, amount: float, epoch: int) -> None:
    """Debit an agent, refusing overdrafts and frozen agents."""
    if agent_id in ledger.frozen:
        raise PermissionError(f"{agent_id} is frozen")
    balance = ledger.balances.get(agent_id, 0.0)
    if amount > balance:
        raise ValueError("insufficient funds")
    ledger.balances[agent_id] = balance - amount
    ledger.history.append(Entry(agent_id, -amount, epoch))


def transfer(ledger: Ledger, src: str, dst: str, amount: float, epoch: int) -> None:
    """Move funds between agents atomically."""
    withdraw(ledger, src, amount, epoch)
    deposit(ledger, dst, amount, epoch)


def apply_tax(amount: float, rate: float) -> float:
    """Return the tax owed on an amount; rate must lie in [0, 1]."""
    if not 0.0 <= rate <= 1.0:
        raise ValueError("rate must be in [0, 1]")
    return amount * rate


def epoch_entries(ledger: Ledger, start: int, end: int) -> List[Entry]:
    """Entries with start <= epoch < end (half-open window)."""
    return [e for e in ledger.history if start <= e.epoch < end]


def last_n_amounts(ledger: Ledger, agent_id: str, n: int) -> List[float]:
    """The agent's n most recent amounts, newest last."""
    amounts = [e.amount for e in ledger.history if e.agent_id == agent_id]
    return amounts[-n:] if n > 0 else []


def mean_balance(ledger: Ledger) -> float:
    """Mean balance across agents; 0.0 for an empty ledger."""
    if not ledger.balances:
        return 0.0
    return sum(ledger.balances.values()) / len(ledger.balances)


def memo_prefix(entry: Entry, width: int) -> str:
    """First ``width`` characters of the memo, or '' when there is none."""
    if entry.memo is None:
        return ""
    return entry.memo[:width]


def top_holders(ledger: Ledger, k: int) -> List[str]:
    """The k agents with the largest balances, largest first, ties by id."""
    ranked = sorted(ledger.balances.items(), key=lambda kv: (-kv[1], kv[0]))
    return [agent for agent, _ in ranked[:k]]


def freeze_if_overdrawn(ledger: Ledger, limit: float) -> List[str]:
    """Freeze every agent whose balance is below -limit; return who was frozen."""
    newly = []
    for agent, balance in ledger.balances.items():
        if balance < -limit and agent not in ledger.frozen:
            ledger.frozen.add(agent)
            newly.append(agent)
    return newly


def split_evenly(amount: float, agents: List[str]) -> Dict[str, float]:
    """Divide an amount equally; an empty agent list gets nothing."""
    if not agents:
        return {}
    share = amount / len(agents)
    return dict.fromkeys(agents, share)


def merge_ledgers(a: Ledger, b: Ledger) -> Ledger:
    """A new ledger holding both histories and summed balances; inputs unchanged."""
    merged = Ledger(balances=dict(a.balances), history=list(a.history), frozen=set(a.frozen))
    for agent, balance in b.balances.items():
        merged.balances[agent] = merged.balances.get(agent, 0.0) + balance
    merged.history.extend(b.history)
    merged.frozen |= b.frozen
    return merged
