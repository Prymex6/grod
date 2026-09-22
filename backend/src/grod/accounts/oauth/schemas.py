"""Bodies of the OpenID Connect endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, Field

from grod.accounts.oauth.models import CLIENT_NAME_MAX_LENGTH
from grod.accounts.schemas import ApiModel

MAX_REDIRECT_URIS = 10


class ClientRegistration(ApiModel):
    """Register an application that may sign people in through this instance."""

    name: str = Field(min_length=1, max_length=CLIENT_NAME_MAX_LENGTH)
    redirect_uris: list[AnyHttpUrl] = Field(min_length=1, max_length=MAX_REDIRECT_URIS)
    scopes: list[str] = Field(min_length=1)
    # Browser and mobile apps cannot keep a secret and rely on PKCE alone.
    confidential: bool = True


class ClientView(ApiModel):
    """An application as the console shows it."""

    id: UUID
    client_id: str
    name: str
    redirect_uris: list[str]
    scopes: list[str]
    confidential: bool
    created_at: datetime


class NewClientView(ClientView):
    """The same, plus the secret, which is shown only once."""

    client_secret: str | None


class AuthorizationView(ApiModel):
    """An application that may sign this account in."""

    client_id: str
    name: str
    scopes: list[str]
    granted_at: datetime


class ConsentRequestView(ApiModel):
    """What the consent screen needs to show."""

    client_name: str
    scopes: list[str]


class ConsentDecision(ApiModel):
    """Where the browser should go after the decision."""

    redirect_to: str


class TokenResponse(ApiModel):
    """Answer of the token endpoint, in the names the standard requires."""

    access_token: str = Field(serialization_alias="access_token")
    token_type: str = Field(default="Bearer", serialization_alias="token_type")
    expires_in: int = Field(serialization_alias="expires_in")
    scope: str = Field(serialization_alias="scope")
    id_token: str | None = Field(default=None, serialization_alias="id_token")
    refresh_token: str | None = Field(default=None, serialization_alias="refresh_token")
