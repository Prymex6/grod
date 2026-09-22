"""Request and response bodies of the account endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

from grod.accounts.models import DISPLAY_NAME_MAX_LENGTH
from grod.accounts.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

TOTP_CODE_LENGTH = 6
TOTP_CODE_PATTERN = r"^\d{6}$"


class ApiModel(BaseModel):
    """Base of every body on the wire: JSON uses camelCase, Python snake_case."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AccountView(ApiModel):
    """Account data the console may show."""

    id: UUID
    email: EmailStr
    login: str
    display_name: str
    totp_enabled: bool
    created_at: datetime


class RegisterRequest(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class TotpLoginRequest(ApiModel):
    pending_token: str = Field(min_length=1, max_length=256)
    code: str = Field(pattern=TOTP_CODE_PATTERN)


class TotpCodeRequest(ApiModel):
    code: str = Field(pattern=TOTP_CODE_PATTERN)


class SignedIn(ApiModel):
    """The password step was enough and the session cookie is set."""

    status: Literal["signed_in"] = "signed_in"
    account: AccountView


class TotpRequired(ApiModel):
    """The account has two-factor enabled, so a code is still needed."""

    status: Literal["totp_required"] = "totp_required"
    pending_token: str


class SessionView(ApiModel):
    """A live session of the signed-in account."""

    created_at: datetime
    user_agent: str
    current: bool


class PasswordResetRequest(ApiModel):
    email: EmailStr


class PasswordResetConfirm(ApiModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class ClosedSessions(ApiModel):
    """How many other sessions were signed out."""

    closed: int


class TotpEnrollment(ApiModel):
    """Secret to put into an authenticator app, before it is confirmed."""

    secret: str
    provisioning_uri: str
