"""Turning "you already have enough" into an answer the console understands."""

from fastapi import HTTPException, status

from grod.quotas.service import OverQuotaError

DETAIL = "This account already holds as much as it may"


def refusal(error: OverQuotaError) -> HTTPException:
    """The answer given when a limit is reached, whatever the limit was."""
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail=f"{DETAIL}: {error.thing} ({error.limit})",
    )
