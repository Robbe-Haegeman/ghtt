"""Push updated assignment code to student repositories and open pull requests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer
from github import GithubException
from github.Repository import Repository

from .assignment import AssignmentContext, require_source
from .git import GitError, clone_branch, commit_all, list_local_branches, push_branch
from .github import clone_url_for, explain_github_error
from .prompt import Confirmer
from .report import TargetReport
from .student_list import RepositoryTarget
from .templates import render_tree

# ==============================================================================
# create-pr
# ==============================================================================


def create_pull_requests(
    context: AssignmentContext,
    branch: str,
    title: str,
    body: str,
    branch_already_pushed: bool,
    per_repository: bool,
    force_push: bool,
    assume_yes: bool,
) -> TargetReport:
    """Open one pull request per target, from a shared or a per-repository branch.

    The shared mode pushes the same source branch to every repository, which is
    how a class-wide correction or a new assignment is handed out. The
    per-repository mode renders the source separately for each target, which is
    how unique content reaches a student without leaking another student's.
    """
    settings = context.settings
    default_branch = settings.config.default_branch

    source: Path | None = None
    if not branch_already_pushed:
        source = require_source(settings)
        if default_branch not in list_local_branches(source):
            raise GitError(
                f"The source repository {source} has no branch {default_branch!r}. "
                "Name the right branch with --default-branch."
            )
    if per_repository and branch_already_pushed:
        raise GitError(
            "--per-repository renders and pushes each repository separately, so "
            "it cannot be combined with --branch-already-pushed."
        )

    typer.secho(f"# Branch: '{branch}'", fg=typer.colors.GREEN)
    typer.secho(f"# Title: '{title}'", fg=typer.colors.GREEN)
    typer.secho(f"# Message: '{body}'", fg=typer.colors.GREEN)
    typer.secho(f"# Base branch: '{default_branch}'", fg=typer.colors.GREEN)
    if branch_already_pushed:
        typer.secho("# The branch has been pushed already.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"# Source directory: '{source}'", fg=typer.colors.GREEN)

    confirmer = Confirmer("create the pull request for", assume_yes, settings.dry_run)

    processed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for target in context.targets:
        repository = context.existing(target)
        if repository is None:
            typer.secho(
                f"Warning: repository {target.name} does not exist; skipping.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            failed.append(f"{target.name}: repository does not exist")
            continue

        if not confirmer.should_proceed(target.url):
            skipped.append(target.name)
            continue

        if settings.dry_run:
            if not branch_already_pushed:
                typer.echo(f"would push {default_branch} to {target.name}:{branch}")
            typer.echo(
                f"would open a pull request '{title}' on {target.name} "
                f"from {branch} into {default_branch}"
            )
            skipped.append(target.name)
            continue

        clone_url = clone_url_for(repository, settings.transport)
        try:
            if source is not None and per_repository:
                push_rendered_source(
                    context, target, source, clone_url, branch, force_push
                )
            elif source is not None:
                typer.secho(
                    f"Pushing {default_branch} to {target.name}:{branch}",
                    fg=typer.colors.GREEN,
                )
                push_branch(
                    source,
                    clone_url,
                    default_branch,
                    branch,
                    settings.transport,
                    settings.git_token,
                    force=force_push,
                )
        except GitError as error:
            # A rejected push is nearly always a branch that moved on remotely,
            # so say what to do rather than only repeating Git's own wording.
            typer.secho(
                f"Warning: could not push to {target.name}: {error}\n"
                "If the branch already exists with different history, rerun with "
                "--force-push to overwrite it.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            failed.append(f"{target.name}: push was rejected")
            continue

        try:
            opened = open_pull_request(
                repository, target, branch, title, body, default_branch
            )
        except GithubException as error:
            explained = explain_github_error(
                error, "create a pull request on", target.name
            )
            typer.secho(f"Warning: {explained}", fg=typer.colors.YELLOW, err=True)
            failed.append(f"{target.name}: {explained}")
            continue

        # Pushing to the branch of an existing pull request updates that pull
        # request, so the target was still acted on even though no new one was
        # opened. Only a run that did neither has nothing to report.
        if opened or source is not None:
            processed.append(target.name)
        else:
            skipped.append(target.name)

    return TargetReport(
        processed=tuple(processed), skipped=tuple(skipped), failed=tuple(failed)
    )


def push_rendered_source(
    context: AssignmentContext,
    target: RepositoryTarget,
    source: Path,
    clone_url: str,
    branch: str,
    force_push: bool,
) -> None:
    """Render the source for one target only and push it as that target's branch.

    Each target is rendered in its own temporary clone, so no student's data can
    reach another student's repository and the source is left untouched.
    """
    settings = context.settings
    with tempfile.TemporaryDirectory(prefix="ghtt-") as directory:
        workspace = Path(directory) / target.name
        clone_branch(source, settings.config.default_branch, workspace)
        rendered = render_tree(workspace, target, clone_url)
        if rendered:
            typer.echo(f"Rendered {len(rendered)} template files for {target.name}")
        commit_all(workspace, f"Update assignment for {target.name}")
        typer.secho(
            f"Pushing rendered source to {target.name}:{branch}", fg=typer.colors.GREEN
        )
        push_branch(
            workspace,
            clone_url,
            "HEAD",
            branch,
            settings.transport,
            settings.git_token,
            force=force_push,
        )


def open_pull_request(
    repository: Repository,
    target: RepositoryTarget,
    branch: str,
    title: str,
    body: str,
    base_branch: str,
) -> bool:
    """Open a pull request unless an open one already covers this branch pair.

    Returns whether a new pull request was created. Pushing to the branch of an
    existing pull request already updates it, so opening a second one would only
    split the same review in two.
    """
    for existing in repository.get_pulls(state="open", base=base_branch):
        if existing.head.ref == branch:
            typer.secho(
                f"Pull request {existing.html_url} already exists for "
                f"{branch} -> {base_branch}; it was updated by the push.",
                fg=typer.colors.YELLOW,
            )
            return False

    pull_request = repository.create_pull(
        title=title, body=body, base=base_branch, head=branch
    )
    typer.secho(
        f"Created pull request {pull_request.html_url} for {target.name}",
        fg=typer.colors.GREEN,
    )
    return True
