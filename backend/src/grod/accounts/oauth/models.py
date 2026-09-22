"""Applications that let people sign in through this instance."""

from uuid import UUID

from sqlalchemy import ARRAY, Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from grod.db import TimestampedTable

CLIENT_NAME_MAX_LENGTH = 100
REDIRECT_URI_MAX_LENGTH = 2048


class OAuthClient(TimestampedTable):
    """An application registered as an OpenID Connect client."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(CLIENT_NAME_MAX_LENGTH))
    # Public clients (browser and mobile apps) have no secret and rely on PKCE.
    client_secret_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(String(REDIRECT_URI_MAX_LENGTH)))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    @property
    def is_confidential(self) -> bool:
        """True when the application can keep a secret."""
        return self.client_secret_hash is not None


class OAuthGrant(TimestampedTable):
    """An account has allowed an application to sign it in."""

    __tablename__ = "oauth_grants"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_oauth_grants_user_client"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("oauth_clients.id", ondelete="CASCADE"), index=True
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
