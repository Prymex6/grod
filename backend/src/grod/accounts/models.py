"""Tables owned by the accounts module."""

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

EMAIL_MAX_LENGTH = 320
DISPLAY_NAME_MAX_LENGTH = 100
LOGIN_MAX_LENGTH = 64


class User(TimestampedTable):
    """An account on this instance."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), unique=True, index=True)
    # Handle used in repository addresses, for example /bartek/grod.git
    login: Mapped[str] = mapped_column(String(LOGIN_MAX_LENGTH), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(DISPLAY_NAME_MAX_LENGTH))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # Set while enrolling an authenticator app; two-factor is required only once confirmed.
    totp_secret: Mapped[str | None] = mapped_column(String(64), default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
