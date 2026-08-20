"""The confirmation vocabulary is part of the contract with existing courses."""

from __future__ import annotations

from typing import Any

import pytest
import typer

from ghtt.prompt import Aborted, Confirmer


def answers(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> list[str]:
    """Answer prompts in order and record every question that was asked."""
    asked: list[str] = []

    def fake_prompt(text: str, **_: Any) -> str:
        asked.append(text)
        return replies.pop(0)

    monkeypatch.setattr(typer, "prompt", fake_prompt)
    return asked


def test_all_answers_for_every_remaining_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answers(monkeypatch, ["all"])
    confirmer = Confirmer("create the repository")

    decisions = [confirmer.should_proceed(name) for name in ("one", "two", "three")]

    assert decisions == [True, True, True]
    assert len(asked) == 1


def test_none_declines_every_remaining_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answers(monkeypatch, ["none"])
    confirmer = Confirmer("create the repository")

    decisions = [confirmer.should_proceed(name) for name in ("one", "two")]

    assert decisions == [False, False]
    assert len(asked) == 1


def test_y_and_n_decide_only_their_own_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers(monkeypatch, ["y", "n", "y"])
    confirmer = Confirmer("create the repository")

    assert [confirmer.should_proceed(name) for name in ("one", "two", "three")] == [
        True,
        False,
        True,
    ]


def test_abort_stops_the_whole_command(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, ["abort"])
    confirmer = Confirmer("create the repository")

    with pytest.raises(Aborted):
        confirmer.should_proceed("one")


def test_yes_asks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, [])
    confirmer = Confirmer("create the repository", assume_yes=True)

    assert confirmer.should_proceed("one") is True
    assert asked == []


def test_a_dry_run_asks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, [])
    confirmer = Confirmer("create the repository", dry_run=True)

    assert confirmer.should_proceed("one") is True
    assert asked == []


def test_a_command_that_must_always_ask_ignores_yes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answers(monkeypatch, ["y", "y"])
    confirmer = Confirmer("delete", assume_yes=True, always_ask=True)

    assert [confirmer.should_proceed(name) for name in ("one", "two")] == [True, True]
    assert len(asked) == 2
