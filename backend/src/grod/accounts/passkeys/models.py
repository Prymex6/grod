"""Passkeys (WebAuthn credentials) registered to an account."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

LABEL_MAX_LENGTH = 100


class Passkey(TimestampedTable):
    """One authenticator (phone, laptop or security key) of an account."""

    __tablename__ = "passkeys"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    # Authenticators count their uses; a counter going backwards means trouble.
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(LABEL_MAX_LENGTH))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
