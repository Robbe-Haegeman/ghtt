"""The shared confirmation vocabulary for bulk operations over many targets."""

from __future__ import annotations

from enum import StrEnum

import click
import typer

from .errors import GhttError


class Aborted(GhttError):
    """The user asked to stop the whole command at a confirmation prompt."""


class BulkChoice(StrEnum):
    """The answers accepted at a per-target confirmation prompt.

    These spellings are part of the compatibility contract with the previous
    release: existing course notes tell teachers to answer ``all`` or ``none``.
    """

    YES = "y"
    ALL = "all"
    NO = "n"
    NONE = "none"
    ABORT = "abort"


#: Offered when a single answer may stand in for every remaining target.
BULK_CHOICES = (
    BulkChoice.YES,
    BulkChoice.ALL,
    BulkChoice.NO,
    BulkChoice.NONE,
    BulkChoice.ABORT,
)

#: Offered when each target must be decided on its own, such as for deletion.
SINGLE_CHOICES = (BulkChoice.YES, BulkChoice.NO, BulkChoice.ABORT)


class Confirmer:
    """Ask about one target at a time, remembering ``all`` and ``none`` answers."""

    def __init__(
        self,
        action: str,
        assume_yes: bool = False,
        dry_run: bool = False,
        always_ask: bool = False,
    ) -> None:
        self.action = action
        # Deletion must be decided per repository, so it never offers an answer
        # that covers the remaining targets and never honours --yes.
        self.always_ask = always_ask and not dry_run
        self.choices = SINGLE_CHOICES if self.always_ask else BULK_CHOICES
        # A dry run performs no mutation, so prompting for each target would
        # only slow down the review that the dry run exists to support.
        self.remembered: BulkChoice | None = None
        if (assume_yes or dry_run) and not self.always_ask:
            self.remembered = BulkChoice.ALL

    def should_proceed(self, subject: str) -> bool:
        """Decide whether one target should be processed, prompting when needed."""
        if self.remembered is BulkChoice.ALL:
            return True
        if self.remembered is BulkChoice.NONE:
            return False

        answer = BulkChoice(
            typer.prompt(
                f'Do you want to {self.action} "{subject}"?',
                type=click.Choice(
                    [choice.value for choice in self.choices], case_sensitive=False
                ),
                show_choices=True,
                default=BulkChoice.NO.value,
            )
        )

        if answer is BulkChoice.ABORT:
            raise Aborted("Aborted at a confirmation prompt; nothing further was done.")
        if answer is BulkChoice.ALL:
            self.remembered = BulkChoice.ALL
            return True
        if answer is BulkChoice.NONE:
            self.remembered = BulkChoice.NONE
            return False
        if answer is BulkChoice.NO:
            typer.secho(f"Skipping {subject}", fg=typer.colors.YELLOW)
            return False
        return True
