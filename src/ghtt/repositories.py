"""Create, delete, and rename the repositories of an organization."""

from __future__ import annotations

import re

import typer
from github import GithubException

from .assignment import AssignmentContext
from .errors import GhttError
from .github import (
    connect_github,
    explain_github_error,
    load_organization,
    load_repositories,
)
from .prompt import Confirmer
from .report import TargetReport
from .settings import Settings

# ==============================================================================
# delete-repos
# ==============================================================================


class DeletionNotEnabled(GhttError):
    """Repository deletion was requested without both required opt-ins."""


def require_deletion_enabled(settings: Settings, destroy_data: bool) -> None:
    """Check both deletion safeguards before anything is selected or contacted.

    Deleting a student repository destroys work that cannot be recovered, so it
    takes two deliberate and independent statements of intent: one on the
    command line for this run, and one in the project settings for this course.
    """
    typer.secho("*** This command will delete repositories! ***", fg=typer.colors.RED)
    typer.secho("*** It will destroy data irrecoverably! ***", fg=typer.colors.RED)
    typer.secho(
        '\nLifesaver: consider "ghtt assignment rename-repo" to rename '
        "repositories instead of deleting them.\n",
        fg=typer.colors.GREEN,
    )

    if not destroy_data:
        raise DeletionNotEnabled(
            "Add --destroy-data to confirm that this command may destroy data."
        )
    if not settings.config.enable_repo_delete:
        raise DeletionNotEnabled(
            "Add --enable-repo-delete, or the line 'enable-repo-delete: true' to "
            "your ghtt.yaml, to enable the delete-repos command."
        )


def delete_repositories(context: AssignmentContext) -> TargetReport:
    """Delete every selected repository after confirming each one separately."""
    dry_run = context.settings.dry_run
    # --yes deliberately has no effect here: every repository is confirmed on
    # its own, because one wrong answer would destroy a whole course.
    confirmer = Confirmer(
        "permanently delete the repository and all its data at",
        assume_yes=False,
        dry_run=dry_run,
        always_ask=True,
    )

    processed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for target in context.targets:
        repository = context.existing(target)
        if repository is None:
            typer.secho(
                f"Repository {target.name} does not exist; nothing to delete.",
                fg=typer.colors.YELLOW,
            )
            skipped.append(target.name)
            continue

        if not confirmer.should_proceed(target.url):
            skipped.append(target.name)
            continue

        if dry_run:
            typer.echo(f"would permanently delete {target.url}")
            skipped.append(target.name)
            continue

        typer.secho(f"Deleting repository {target.url}", fg=typer.colors.RED)
        try:
            repository.delete()
        except GithubException as error:
            explained = explain_github_error(error, "delete repository", target.name)
            typer.secho(f"Warning: {explained}", fg=typer.colors.YELLOW, err=True)
            failed.append(f"{target.name}: {explained}")
            continue
        processed.append(target.name)

    return TargetReport(
        processed=tuple(processed), skipped=tuple(skipped), failed=tuple(failed)
    )


# ==============================================================================
# rename-repo
# ==============================================================================


class RenameError(GhttError):
    """A rename pattern or replacement cannot be applied safely."""


def rename_repositories(
    settings: Settings, match: str, replace: str, assume_yes: bool
) -> TargetReport:
    """Rename every organization repository whose name matches a regular expression.

    Unlike the other assignment commands this one deliberately works on the whole
    organization rather than on the student list, because its main use is
    tidying up repositories that the student list no longer describes.
    """
    try:
        pattern = re.compile(match)
    except re.error as error:
        raise RenameError(
            f"Invalid --match regular expression {match!r}: {error}"
        ) from error

    client = connect_github(settings.connection, settings.token)
    organization = load_organization(client, settings.connection.organization)
    repositories = load_repositories(organization)

    # Every rename is planned before any is applied, so a replacement that would
    # collide with an existing repository is caught while nothing has changed.
    planned: list[tuple[str, str]] = []
    for name in sorted(repositories):
        repository = repositories[name]
        if not pattern.match(repository.name):
            continue
        try:
            new_name = pattern.sub(replace, repository.name)
        except re.error as error:
            raise RenameError(
                f"Invalid --replace replacement {replace!r}: {error}"
            ) from error
        if not new_name:
            raise RenameError(
                f"Renaming {repository.name} with {replace!r} would leave it nameless"
            )
        if new_name == repository.name:
            continue
        planned.append((repository.name, new_name))

    if not planned:
        typer.secho(
            f"No repository in {organization.login} matches {match!r}.",
            fg=typer.colors.YELLOW,
        )
        return TargetReport()

    typer.secho(
        f"# {len(planned)} repositories will be renamed:", fg=typer.colors.GREEN
    )
    for old_name, new_name in planned:
        typer.echo(f"  {old_name} -> {new_name}")

    taken = set(repositories)
    confirmer = Confirmer("rename", assume_yes, settings.dry_run)

    processed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for old_name, new_name in planned:
        if new_name.lower() in taken:
            typer.secho(
                f"Warning: {new_name} already exists in {organization.login}; "
                f"leaving {old_name} alone.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            failed.append(f"{old_name}: {new_name} already exists")
            continue

        if not confirmer.should_proceed(f"{old_name} to {new_name}"):
            skipped.append(old_name)
            continue

        if settings.dry_run:
            typer.echo(f"would rename {old_name} to {new_name}")
            skipped.append(old_name)
            continue

        try:
            repositories[old_name.lower()].edit(name=new_name)
        except GithubException as error:
            explained = explain_github_error(error, "rename repository", old_name)
            typer.secho(f"Warning: {explained}", fg=typer.colors.YELLOW, err=True)
            failed.append(f"{old_name}: {explained}")
            continue

        # The new name now occupies a slot, so a later rename cannot collide
        # with it even though the listing was fetched before this run started.
        taken.discard(old_name.lower())
        taken.add(new_name.lower())
        processed.append(f"{old_name} -> {new_name}")

    return TargetReport(
        processed=tuple(processed), skipped=tuple(skipped), failed=tuple(failed)
    )
