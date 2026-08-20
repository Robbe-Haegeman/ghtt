"""Help rendering must be safe before any config or service setup exists."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ghtt.__main__ import app

runner = CliRunner()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["assignment", "--help"],
        ["assignment", "create-repos", "--help"],
        ["assignment", "create-pr", "--help"],
        ["assignment", "create-issues", "--help"],
        ["assignment", "pull", "--help"],
        ["assignment", "grant", "--help"],
        ["assignment", "remove-grant", "--help"],
        ["assignment", "delete-repos", "--help"],
        ["assignment", "rename-repo", "--help"],
        ["config", "--help"],
        ["config", "schema", "--help"],
        ["search", "--help"],
        ["util", "--help"],
        ["util", "grep-in", "--help"],
        ["util", "branches-to-folders", "--help"],
    ],
)
def test_help_is_available_without_config(arguments: list[str]) -> None:
    result = runner.invoke(app, arguments)

    assert result.exit_code == 0, result.output
    assert result.exception is None
