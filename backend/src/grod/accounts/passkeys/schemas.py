"""Bodies of the passkey endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from grod.accounts.passkeys.models import LABEL_MAX_LENGTH
from grod.accounts.schemas import ApiModel


class PasskeyView(ApiModel):
    """A registered authenticator as the console shows it."""

    id: UUID
    label: str
    created_at: datetime
    last_used_at: datetime | None


class PasskeyOptions(ApiModel):
    """Options for the browser, plus the handle of the stored challenge."""

    handle: str
    # Passed to navigator.credentials as the WebAuthn standard defines it.
    options: dict[str, Any]


class PasskeyRegistration(ApiModel):
    """What the browser returns after creating a passkey."""

    handle: str
    credential: dict[str, Any]
    label: str | None = Field(default=None, max_length=LABEL_MAX_LENGTH)


class PasskeyAuthentication(ApiModel):
    """What the browser returns after signing in with a passkey."""

    handle: str
    credential: dict[str, Any]
