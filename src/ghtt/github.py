"""Connect to GitHub.com or GitHub Enterprise and explain expected API failures."""

from __future__ import annotations

from urllib.parse import urlparse

from github import Auth, Github, GithubException
from pydantic import BaseModel, ConfigDict

# ==============================================================================
# Connection Values
# ==============================================================================


class GitHubError(Exception):
    """A GitHub request cannot complete the requested action."""


class GitHubConnection(BaseModel):
    """The API endpoint and target organization derived from user input."""

    model_config = ConfigDict(frozen=True)

    api_url: str | None
    organization: str


# ==============================================================================
# URL Interpretation
# ==============================================================================


def parse_github_url(url: str, organization: str | None = None) -> GitHubConnection:
    """Accept a GitHub host URL and the legacy form that includes an organization."""
    normalized_url = url if "://" in url else f"https://{url}"
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise GitHubError(f"Invalid GitHub URL: {url!r}")

    path_parts = [part for part in parsed.path.split("/") if part]
    legacy_organization = path_parts[0] if path_parts else None
    target_organization = organization or legacy_organization
    if not target_organization:
        raise GitHubError(
            "Missing organization. Supply --organization or use a legacy --url "
            "that includes the organization path."
        )
    if len(path_parts) > 1:
        raise GitHubError(
            f"GitHub URL {url!r} may contain only one legacy organization path"
        )

    # PyGithub uses its own GitHub.com default. Enterprise API calls require
    # the API v3 endpoint but retain the host and scheme the user selected.
    api_url = None
    if parsed.hostname != "github.com":
        api_url = f"{parsed.scheme}://{parsed.netloc}/api/v3"
    return GitHubConnection(api_url=api_url, organization=target_organization)


# ==============================================================================
# API Connection
# ==============================================================================


def connect_github(connection: GitHubConnection, token: str) -> Github:
    """Create an authenticated client only when a command is ready to make API calls."""
    if not token:
        raise GitHubError("Missing token. Supply it with --token.")

    authentication = Auth.Token(token)
    if connection.api_url is None:
        return Github(auth=authentication)
    return Github(auth=authentication, base_url=connection.api_url)


def explain_github_error(
    error: GithubException, action: str, target: str
) -> GitHubError:
    """Turn common opaque API failures into an action and target-specific message."""
    if error.status == 401:
        return GitHubError(
            f"Cannot {action} {target}: authentication failed; check --token."
        )
    if error.status == 403:
        return GitHubError(
            f"Cannot {action} {target}: permission denied; check the token scopes "
            "and organization role."
        )
    if error.status == 404:
        return GitHubError(
            f"Cannot {action} {target}: it was not found or the token cannot access it."
        )
    return GitHubError(f"Cannot {action} {target}: GitHub returned {error.status}.")
