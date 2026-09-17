"""Contract tests for clock, shared budget, and error-propagation measurement."""

import json
from pathlib import Path

import pytest

from experiments.deadline_pressure import (
    Reply,
    SmokeClient,
    load_config,
    run,
    run_episode,
)


class ScriptClient:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = []

    def generate(self, prompt, *, seed, limit):
        context = json.loads(prompt)
        self.calls.append((context, seed, limit))
        if context["role"] == "worker":
            value = {"answer": context["record"]}
        elif context["role"] == "downstream":
            value = {"answer": context["board"][-1] if context["board"] else None}
        else:
            value = next(self.actions, {"action": "SUBMIT", "answer": 47})
        return Reply(json.dumps(value), limit, 10)


@pytest.fixture
def cfg():
    return load_config(Path("scenarios/deadline_pressure.yaml"))


def test_deadline_blocks_verification_without_revealing_source(cfg):
    cfg["deadlines"]["tight"] = 3
    client = ScriptClient([{"action": "VERIFY"}, {"action": "SHARE", "answer": 42}])
    result = run_episode(cfg, client, "tight", 42)
    assert result["events"][0]["reason"] == "deadline"
    assert "authoritative_records" not in result["events"][0]
    assert result["metrics"]["source_verifications"] == 0
    assert result["metrics"]["unverified_shares"] == 1
    assert result["metrics"]["downstream_peer_error"] == 1
    assert result["elapsed_ticks"] <= 3


def test_verified_share_is_distinct_from_correct_share(cfg):
    result = run_episode(
        cfg,
        ScriptClient(
            [
                {"action": "VERIFY"},
                {"action": "SHARE", "answer": 42},
            ]
        ),
        "relaxed",
        42,
    )
    assert result["metrics"]["source_verifications"] == 1
    assert result["metrics"]["unverified_shares"] == 0
    assert result["metrics"]["incorrect_shares"] == 1


def test_downstream_error_requires_that_error_was_published(cfg):
    class GuessingClient(ScriptClient):
        def generate(self, prompt, *, seed, limit):
            if json.loads(prompt)["role"] == "downstream":
                return Reply('{"answer":42}', limit, 10)
            return super().generate(prompt, seed=seed, limit=limit)

    result = run_episode(
        cfg,
        GuessingClient(
            [
                {"action": "SHARE", "answer": 47},
            ]
        ),
        "tight",
        42,
    )
    assert result["downstream_answer"] == 42
    assert result["metrics"]["downstream_peer_error"] == 0


def test_workers_cannot_overspend_shared_allowance(cfg):
    cfg["generated_token_budget"] = 135
    client = ScriptClient([{"action": "DELEGATE"}])
    result = run_episode(cfg, client, "relaxed", 42)
    workers = [e for e in result["exchanges"] if e["prompt"]["role"] == "worker"]
    assert [e["limit"] for e in workers] == [2, 2, 2]
    assert result["metrics"]["generated_tokens"] == 135
    assert result["metrics"]["delegated_workers"] == 3
    assert result["events"][0]["worker_answers"] == [17, 19, 11]


def test_invalid_actions_consume_time_and_never_publish(cfg):
    result = run_episode(
        cfg,
        ScriptClient(
            [
                {"action": "SHARE", "answer": True},
                {"action": "UNKNOWN"},
            ]
        ),
        "tight",
        42,
    )
    assert result["metrics"]["invalid_responses"] == 2
    assert result["metrics"]["shares"] == 0
    assert result["elapsed_ticks"] == 3


def test_backend_cap_violation_is_failure(cfg):
    class BrokenClient:
        def generate(self, prompt, *, seed, limit):
            return Reply("{}", limit + 1, 10)

    with pytest.raises(ValueError, match="violated"):
        run_episode(cfg, BrokenClient(), "tight", 42)


def test_smoke_exports_reproducibly_and_refuses_overwrite(cfg, tmp_path):
    for label in ("a", "b"):
        run(cfg, SmokeClient(), tmp_path / label, smoke=True)
    for name in ("history.json", "metrics.csv", "events.jsonl", "paired_deltas.json"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()
    history = json.loads((tmp_path / "a" / "history.json").read_text())
    assert history["mode"] == "smoke"
    assert len(history["episodes"]) == 10
    with pytest.raises(FileExistsError):
        run(cfg, SmokeClient(), tmp_path / "a", smoke=True)
