"""Templates render against a documented contract and fail loudly on a typo."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghtt.templates import RenderError, render_text, render_tree

from .factories import make_target

TARGET = make_target("course-team-1", students=("ada", "bert"), group="team-1")
CLONE_URL = "https://github.example.edu/course/course-team-1.git"


def test_every_documented_variable_is_available() -> None:
    template = (
        "{{ repo.name }}|{{ organization }}|{{ group }}|{{ clone_url }}|"
        "{{ students | length }}|{{ students[0].username }}|{{ repo.description }}"
    )

    assert render_text(template, TARGET, CLONE_URL) == (
        f"course-team-1|course|team-1|{CLONE_URL}|2|ada|Ada, Bert"
    )


def test_the_legacy_repo_comment_name_still_works() -> None:
    assert render_text("{{ repo.comment }}", TARGET, CLONE_URL) == "Ada, Bert"


def test_an_undefined_variable_is_reported_instead_of_rendered_empty() -> None:
    with pytest.raises(RenderError, match="course-team-1"):
        render_text("Hello {{ typo }}", TARGET, CLONE_URL)


def test_rendering_a_tree_replaces_each_template_with_its_output(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md.jinja").write_text("Clone {{ clone_url }}\n", "utf-8")
    (tmp_path / "docs" / "task.md.jinja").write_text("For {{ group }}\n", "utf-8")
    (tmp_path / "keep.txt").write_text("{{ not a template }}\n", "utf-8")

    rendered = render_tree(tmp_path, TARGET, CLONE_URL)

    assert sorted(path.name for path in rendered) == ["README.md", "task.md"]
    assert (tmp_path / "README.md").read_text("utf-8") == f"Clone {CLONE_URL}\n"
    assert (tmp_path / "docs" / "task.md").read_text("utf-8") == "For team-1\n"
    assert not (tmp_path / "README.md.jinja").exists()
    # A file that is not a template is left exactly as it was.
    assert (tmp_path / "keep.txt").read_text("utf-8") == "{{ not a template }}\n"


def test_git_data_is_never_treated_as_course_content(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook.sample.jinja").write_text("{{ typo }}\n", "utf-8")

    assert render_tree(tmp_path, TARGET, CLONE_URL) == ()
    assert (tmp_path / ".git" / "hook.sample.jinja").exists()
