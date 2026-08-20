"""The offline command shell for ghtt.

Command callbacks intentionally do not load configuration or construct service
clients. Typer invokes these callbacks to render help too, so side effects here
would make the documented offline-help guarantee impossible to keep.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    help="Manage GitHub-based coursework and exams.",
    no_args_is_help=True,
)
assignment_app = typer.Typer(
    help="Manage student or group repositories.",
    no_args_is_help=True,
)
config_app = typer.Typer(
    help="Inspect ghtt configuration support.",
    no_args_is_help=True,
)
util_app = typer.Typer(
    help="Run local file and Git utilities.",
    no_args_is_help=True,
)

ConfigPath = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help="Optional ghtt.yaml file. It is loaded only when a command needs it.",
    ),
]


def rewrite_in_progress(command: str) -> None:
    """Prevent partial commands from being mistaken for successful operations."""
    typer.echo(
        f"The {command} command is not implemented in this rewrite stage.",
        err=True,
    )
    raise typer.Exit(code=2)


@app.callback()
def cli(config: ConfigPath = None) -> None:
    """Run ghtt commands."""


@app.command()
def search() -> None:
    """Search GitHub code and optionally notify by email."""
    rewrite_in_progress("search")


@config_app.command()
def schema() -> None:
    """Print the JSON Schema for this ghtt release."""
    rewrite_in_progress("configuration schema")


@assignment_app.command("create-repos")
def create_repos() -> None:
    """Create repositories from a source Git repository."""
    rewrite_in_progress("create-repos")


@assignment_app.command("create-pr")
def create_pr() -> None:
    """Push a branch and create pull requests."""
    rewrite_in_progress("create-pr")


@assignment_app.command("create-issues")
def create_issues(
    path: Annotated[Path, typer.Argument(help="YAML issue-and-milestone template.")],
) -> None:
    """Create or update issues and milestones from PATH."""
    rewrite_in_progress("create-issues")


@assignment_app.command()
def pull() -> None:
    """Fetch each target repository and report its latest commit."""
    rewrite_in_progress("pull")


@assignment_app.command()
def grant() -> None:
    """Give students repository access."""
    rewrite_in_progress("grant")


@assignment_app.command("remove-grant")
def remove_grant() -> None:
    """Remove student access and pending invitations."""
    rewrite_in_progress("remove-grant")


@assignment_app.command("delete-repos")
def delete_repos() -> None:
    """Permanently delete target repositories after explicit safeguards."""
    rewrite_in_progress("delete-repos")


@assignment_app.command("rename-repo")
def rename_repo() -> None:
    """Rename organization repositories selected by a regular expression."""
    rewrite_in_progress("rename-repo")


@util_app.command("grep-in")
def grep_in(
    path: Annotated[Path, typer.Argument(help="File to search.")],
    strings: Annotated[
        str, typer.Argument(help="Comma-separated strings to search for.")
    ],
) -> None:
    """Print lines from PATH that contain one of STRINGS."""
    rewrite_in_progress("grep-in")


@util_app.command("branches-to-folders")
def branches_to_folders(
    source: Annotated[Path, typer.Argument(help="Local Git repository to expand.")],
) -> None:
    """Clone every local branch into a sibling .expanded directory."""
    rewrite_in_progress("branches-to-folders")


app.add_typer(assignment_app, name="assignment")
app.add_typer(config_app, name="config")
app.add_typer(util_app, name="util")


if __name__ == "__main__":
    app()
