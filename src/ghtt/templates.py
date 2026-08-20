"""Render Jinja templates with the documented data of one repository target."""

from __future__ import annotations

from pathlib import Path

import jinja2

from .defaults import TEMPLATE_SUFFIX
from .errors import GhttError
from .student_list import RepositoryTarget


class RenderError(GhttError):
    """A source template cannot be rendered for a repository target."""


def template_data(target: RepositoryTarget, clone_url: str) -> dict[str, object]:
    """Return the complete set of variables available to a source template.

    This mapping is a documented contract: teachers write templates against it,
    so names are added here rather than assembled differently per command.
    """
    return {
        "clone_url": clone_url,
        "organization": target.organization,
        "group": target.group,
        "students": list(target.students),
        "mentors": list(target.mentors),
        "repo": target,
    }


def render_text(template_text: str, target: RepositoryTarget, clone_url: str) -> str:
    """Render one template string for a target, failing on any unknown variable."""
    environment = jinja2.Environment(
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True
    )
    try:
        return environment.from_string(template_text).render(
            template_data(target, clone_url)
        )
    except jinja2.TemplateError as error:
        raise RenderError(
            f"Cannot render template for {target.name}: {error}"
        ) from error


def render_tree(
    directory: Path, target: RepositoryTarget, clone_url: str
) -> tuple[Path, ...]:
    """Render every ``.jinja`` file in a working copy and drop the suffix.

    The caller is responsible for passing a throwaway copy of the source: each
    rendered file replaces its own template, which must never happen inside the
    teacher's own source repository.
    """
    rendered: list[Path] = []
    for template_path in sorted(directory.rglob(f"*{TEMPLATE_SUFFIX}")):
        # A template stored inside .git is Git's own data, not course content.
        if ".git" in template_path.relative_to(directory).parts:
            continue
        try:
            template_text = template_path.read_text(encoding="utf-8")
        except OSError as error:
            raise RenderError(
                f"Cannot read template {template_path}: {error}"
            ) from error

        output = render_text(template_text, target, clone_url)
        destination = template_path.with_suffix("")
        try:
            destination.write_text(output, encoding="utf-8")
            template_path.unlink()
        except OSError as error:
            raise RenderError(
                f"Cannot write rendered file {destination}: {error}"
            ) from error
        rendered.append(destination)
    return tuple(rendered)
