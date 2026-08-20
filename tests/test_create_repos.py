"""create-repos seeds real repositories without ever touching the source."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ghtt.config import Config, RepositoryConfig
from ghtt.errors import GhttError
from ghtt.repositories import (
    BranchProtectionError,
    create_repositories,
    validate_protected_branches,
)
from ghtt.settings import Settings

from .factories import (
    make_context,
    make_settings,
    make_target,
    recorded_organization,
)
from .fake_github import FakeRepository
from .local_git import branches_of, commit_count, file_in_branch, git, make_repository


def make_source(tmp_path: Path, template: str | None = None) -> Path:
    """Create a source repository, optionally with one .jinja template in it."""
    source = make_repository(tmp_path / "template")
    if template is not None:
        (source / "README.md.jinja").write_text(template, encoding="utf-8")
        git(source, "add", "-A")
        git(source, "commit", "-m", "add template")
    return source


def settings_for(source: Path, repos: RepositoryConfig | None = None) -> Settings:
    return make_settings(
        Config(
            source=source,
            default_branch="master",
            repos=repos or RepositoryConfig(),
        )
    )


# ==============================================================================
# Creating and seeding
# ==============================================================================


def test_create_repos_pushes_the_source_and_configures_the_repository(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    context = make_context(
        (make_target("course-team-1", students=("ada", "bert"), group="team-1"),),
        settings=settings_for(source, RepositoryConfig(has_issues=True)),
        local_root=tmp_path / "remote",
    )

    report = create_repositories(context, assume_yes=True)

    organization = recorded_organization(context)
    created = organization.repositories[0]
    assert organization.created[0]["private"] is True
    assert organization.created[0]["has_issues"] is True
    assert created.local_path is not None
    assert branches_of(created.local_path) == ["master"]
    assert created.edits == [{"default_branch": "master", "description": "Ada, Bert"}]
    assert created.branches["master"].protection == {}
    assert report.processed == ("course-team-1",)


def test_templates_are_rendered_per_repository_and_the_source_is_untouched(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path, "Clone {{ repo.name }} from {{ clone_url }}.\n")
    before_branches = branches_of(source)
    before_commits = commit_count(source, "master")
    context = make_context(
        (make_target("course-team-1", students=("ada",), group="team-1"),),
        settings=settings_for(source),
        local_root=tmp_path / "remote",
    )

    create_repositories(context, assume_yes=True)

    created = recorded_organization(context).repositories[0]
    assert created.local_path is not None
    rendered = file_in_branch(created.local_path, "master", "README.md")
    assert "Clone course-team-1 from" in rendered
    # The template file itself is replaced by its rendered output.
    with pytest.raises(subprocess.CalledProcessError):
        file_in_branch(created.local_path, "master", "README.md.jinja")
    # Nothing was added to the teacher's own repository.
    assert branches_of(source) == before_branches
    assert commit_count(source, "master") == before_commits
    assert (source / "README.md.jinja").exists()


def test_require_pull_requests_is_applied_to_the_protected_branch(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    context = make_context(
        (make_target("course-team-1", students=("ada",)),),
        settings=settings_for(source, RepositoryConfig(require_pull_requests=True)),
        local_root=tmp_path / "remote",
    )

    create_repositories(context, assume_yes=True)

    created = recorded_organization(context).repositories[0]
    assert created.branches["master"].protection == {
        "required_approving_review_count": 0
    }


# ==============================================================================
# Safety
# ==============================================================================


def test_an_existing_repository_is_skipped_and_never_overwritten(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    existing = FakeRepository("course-team-1")
    context = make_context(
        (make_target("course-team-1", students=("ada",)),),
        (existing,),
        settings=settings_for(source),
        local_root=tmp_path / "remote",
    )

    report = create_repositories(context, assume_yes=True)

    assert recorded_organization(context).created == []
    assert existing.edits == []
    assert report.skipped == ("course-team-1",)
    assert report.failed == ()


def test_a_source_without_the_default_branch_names_the_setting(tmp_path: Path) -> None:
    source = make_repository(tmp_path / "template", default_branch="main")
    context = make_context(
        (make_target("course-team-1", students=("ada",)),),
        settings=settings_for(source),
        local_root=tmp_path / "remote",
    )

    with pytest.raises(GhttError, match="default-branch: main"):
        create_repositories(context, assume_yes=True)

    assert recorded_organization(context).created == []


def test_a_source_that_is_not_a_repository_is_rejected(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    context = make_context(
        (make_target("course-team-1", students=("ada",)),),
        settings=settings_for(plain),
    )

    with pytest.raises(GhttError, match="not a Git repository"):
        create_repositories(context, assume_yes=True)


def test_a_wildcard_protection_pattern_is_refused_up_front() -> None:
    with pytest.raises(BranchProtectionError, match="rulesets"):
        validate_protected_branches(("release/*",))


def test_an_extra_branch_that_does_not_exist_is_reported_not_ignored(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    context = make_context(
        (make_target("course-team-1", students=("ada",)),),
        settings=settings_for(
            source, RepositoryConfig(protect_branches=("solutions",))
        ),
        local_root=tmp_path / "remote",
    )

    report = create_repositories(context, assume_yes=True)

    assert report.processed == ()
    assert "could not protect solutions" in report.failed[0]


def test_dry_run_creates_nothing(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    settings = make_settings(
        Config(source=source, default_branch="master"), dry_run=True
    )
    context = make_context(
        (make_target("course-team-1", students=("ada",)),),
        settings=settings,
        local_root=tmp_path / "remote",
    )

    report = create_repositories(context, assume_yes=False)

    assert recorded_organization(context).created == []
    assert report.skipped == ("course-team-1",)
