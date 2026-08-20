"""Run local Git commands with an ephemeral HTTPS token URL when requested."""

from __future__ import annotations

import os
import subprocess
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

# ==============================================================================
# Transport Choice
# ==============================================================================


class GitTransport(StrEnum):
    """The two Git transports supported by ghtt."""

    HTTPS = "https"
    SSH = "ssh"


class GitError(Exception):
    """A Git command cannot safely complete the requested operation."""


# ==============================================================================
# Source Safety
# ==============================================================================


def require_git_repository(source: Path) -> None:
    """Reject a source directory before a command changes GitHub or local Git state."""
    # The legacy command explicitly required .git. Keep that visible safety
    # check instead of discovering a non-repository only after a repo is made.
    if not source.is_dir() or not (source / ".git").exists():
        raise GitError(
            f"Source directory {source} is not a Git repository; "
            f"expected {source / '.git'}"
        )


# ==============================================================================
# Git Execution
# ==============================================================================


def run_git(
    arguments: list[str],
    working_directory: Path,
    transport: GitTransport = GitTransport.HTTPS,
    token: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run Git with an argument list and translate failures into a user error."""
    command = ["git", *arguments]
    environment = os.environ.copy()

    # Git accepts HTTPS credentials in the remote URL. The transformed URL is
    # used only for this subprocess; callers must never use it to add a remote.
    if transport is GitTransport.HTTPS and token:
        authenticated_command: list[str] = []
        for argument in command:
            if argument.startswith("https://"):
                parsed = urlsplit(argument)
                credentials = f"x-access-token:{quote(token, safe='')}@{parsed.netloc}"
                argument = urlunsplit(
                    (parsed.scheme, credentials, parsed.path, parsed.query, "")
                )
            authenticated_command.append(argument)
        command = authenticated_command

    result = subprocess.run(
        command,
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip() or result.stdout.strip() or "Git returned no detail"
        )
        safe_detail = detail.replace(token, "[redacted]") if token else detail
        raise GitError(f"Git could not run {' '.join(arguments)}: {safe_detail}")
    return result
