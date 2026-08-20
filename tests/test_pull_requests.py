"""create-pr pushes a branch per target and never duplicates an open pull request."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghtt.config import Config
from ghtt.errors import GhttError
from ghtt.pull_requests import create_pull_requests

from .factories import make_context, make_settings, make_target
from .fake_github import FakeRepository
from .local_git import (
    branches_of,
    file_in_branch,
    git,
    make_bare_repository,
    make_repository,
)


def student_repository(tmp_path: Path, name: str) -> FakeRepository:
    """Create a bare repository that already holds the source history."""
    bare = make_bare_repository(tmp_path / f"{name}.git")
    repository = FakeRepository(name)
    repository.clone_url = str(bare)
    repository.ssh_url = str(bare)
    return repository


def seed(source: Path, repository: FakeRepository) -> None:
    git(source, "push", repository.clone_url, "master:master")


def context_for(
    source: Path, repositories: tuple[FakeRepository, ...], dry_run: bool = False
):
    targets = tuple(
        make_target(repository.name, students=("ada",)) for repository in repositories
    )
    return make_context(
        targets,
        repositories,
        settings=make_settings(
            Config(source=source, default_branch="master"), dry_run=dry_run
        ),
    )


# ==============================================================================
# Shared branch mode
# ==============================================================================


def test_the_same_branch_is_pushed_to_every_repository(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template")
    repositories = tuple(
        student_repository(tmp_path, name) for name in ("course-ada", "course-bert")
    )
    for repository in repositories:
        seed(source, repository)
    context = context_for(source, repositories)

    report = create_pull_requests(
        context,
        branch="lab2",
        title="Lab 2",
        body="Here is lab 2.",
        branch_already_pushed=False,
        per_repository=False,
        force_push=False,
        assume_yes=True,
    )

    for repository in repositories:
        assert repository.clone_url is not None
        assert "lab2" in branches_of(Path(repository.clone_url))
        assert [pull.head.ref for pull in repository.pulls] == ["lab2"]
        assert repository.pulls[0].base.ref == "master"
    assert report.processed == ("course-ada", "course-bert")


def test_branch_already_pushed_only_opens_the_pull_requests(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template")
    repository = student_repository(tmp_path, "course-ada")
    seed(source, repository)
    context = context_for(source, (repository,))

    create_pull_requests(
        context,
        branch="lab2",
        title="Lab 2",
        body="Here is lab 2.",
        branch_already_pushed=True,
        per_repository=False,
        force_push=False,
        assume_yes=True,
    )

    assert repository.clone_url is not None
    assert branches_of(Path(repository.clone_url)) == ["master"]
    assert [pull.head.ref for pull in repository.pulls] == ["lab2"]


def test_an_open_pull_request_is_reused_instead_of_duplicated(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template")
    repository = student_repository(tmp_path, "course-ada")
    seed(source, repository)
    context = context_for(source, (repository,))
    arguments = {
        "branch": "lab2",
        "title": "Lab 2",
        "body": "Here is lab 2.",
        "branch_already_pushed": True,
        "per_repository": False,
        "force_push": False,
        "assume_yes": True,
    }

    create_pull_requests(context, **arguments)
    second = create_pull_requests(context, **arguments)

    assert len(repository.pulls) == 1
    assert second.processed == ()
    assert second.skipped == ("course-ada",)


# ==============================================================================
# Per-repository mode
# ==============================================================================


def test_per_repository_renders_each_target_separately(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template")
    (source / "TASK.md.jinja").write_text(
        "Task for {{ repo.name }} ({{ students[0].username }})\n", encoding="utf-8"
    )
    git(source, "add", "-A")
    git(source, "commit", "-m", "add template")
    repositories = tuple(
        student_repository(tmp_path, name) for name in ("course-ada", "course-bert")
    )
    for repository in repositories:
        seed(source, repository)
    context = context_for(source, repositories)

    create_pull_requests(
        context,
        branch="lab2",
        title="Lab 2",
        body="Here is lab 2.",
        branch_already_pushed=False,
        per_repository=True,
        force_push=False,
        assume_yes=True,
    )

    for repository in repositories:
        rendered = file_in_branch(Path(repository.clone_url), "lab2", "TASK.md")
        assert f"Task for {repository.name}" in rendered
    # Each repository sees only its own rendering.
    assert "course-bert" not in file_in_branch(
        Path(repositories[0].clone_url), "lab2", "TASK.md"
    )
    # And the teacher's source keeps its template untouched.
    assert (source / "TASK.md.jinja").exists()
    assert branches_of(source) == ["master"]


def test_per_repository_cannot_claim_the_branch_is_already_pushed(
    tmp_path: Path,
) -> None:
    source = make_repository(tmp_path / "template")
    context = context_for(source, (student_repository(tmp_path, "course-ada"),))

    with pytest.raises(GhttError, match="cannot be combined"):
        create_pull_requests(
            context,
            branch="lab2",
            title="Lab 2",
            body="Here is lab 2.",
            branch_already_pushed=True,
            per_repository=True,
            force_push=False,
            assume_yes=True,
        )


# ==============================================================================
# Failures
# ==============================================================================


def test_a_rejected_push_fails_only_its_own_repository(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template", branches=("lab2",))
    good = student_repository(tmp_path, "course-ada")
    conflicted = student_repository(tmp_path, "course-bert")
    seed(source, good)
    seed(source, conflicted)
    # The student repository already has a lab2 branch with other history.
    git(source, "push", conflicted.clone_url, "lab2:lab2")
    git(source, "checkout", "master")
    context = context_for(source, (good, conflicted))

    report = create_pull_requests(
        context,
        branch="lab2",
        title="Lab 2",
        body="Here is lab 2.",
        branch_already_pushed=False,
        per_repository=False,
        force_push=False,
        assume_yes=True,
    )

    assert report.processed == ("course-ada",)
    assert report.failed == ("course-bert: push was rejected",)


def test_a_missing_repository_is_reported_and_the_rest_continue(
    tmp_path: Path,
) -> None:
    source = make_repository(tmp_path / "template")
    present = student_repository(tmp_path, "course-ada")
    seed(source, present)
    context = make_context(
        (
            make_target("course-absent", students=("bert",)),
            make_target("course-ada", students=("ada",)),
        ),
        (present,),
        settings=make_settings(Config(source=source, default_branch="master")),
    )

    report = create_pull_requests(
        context,
        branch="lab2",
        title="Lab 2",
        body="Here is lab 2.",
        branch_already_pushed=False,
        per_repository=False,
        force_push=False,
        assume_yes=True,
    )

    assert report.processed == ("course-ada",)
    assert "course-absent" in report.failed[0]


def test_dry_run_pushes_nothing_and_opens_nothing(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template")
    repository = student_repository(tmp_path, "course-ada")
    seed(source, repository)
    context = context_for(source, (repository,), dry_run=True)

    report = create_pull_requests(
        context,
        branch="lab2",
        title="Lab 2",
        body="Here is lab 2.",
        branch_already_pushed=False,
        per_repository=False,
        force_push=False,
        assume_yes=False,
    )

    assert branches_of(Path(repository.clone_url)) == ["master"]
    assert repository.pulls == []
    assert report.skipped == ("course-ada",)
