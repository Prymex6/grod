"""Bodies of the project and token endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from grod.accounts.schemas import ApiModel
from grod.repositories.models import (
    BRANCH_PATTERN_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    SLUG_PATTERN,
    SSH_KEY_MAX_LENGTH,
    SSH_KEY_NAME_MAX_LENGTH,
    TOKEN_NAME_MAX_LENGTH,
    Visibility,
)

COMMIT_MESSAGE_MAX_LENGTH = 1000
BRANCH_MAX_LENGTH = 255


class ProjectCreate(ApiModel):
    """A new project. The address is what appears in the clone URL."""

    slug: str = Field(pattern=SLUG_PATTERN, min_length=1, max_length=SLUG_MAX_LENGTH)
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    visibility: Visibility = Visibility.PRIVATE
    # Address of the group that is to own it; empty means a personal project.
    group: str | None = Field(default=None, max_length=SLUG_MAX_LENGTH)


class AccessView(ApiModel):
    """What the caller may do in a project, so the console shows the right buttons."""

    read: bool
    write: bool
    manage: bool
    own: bool


class ProjectView(ApiModel):
    """A project as the console shows it."""

    id: UUID
    owner_login: str
    slug: str
    name: str
    description: str
    visibility: Visibility
    default_branch: str
    empty: bool
    clone_url: str
    created_at: datetime
    access: AccessView
    stars: int = 0
    starred: bool = False


class RefView(ApiModel):
    """A branch or a tag."""

    name: str
    commit: str


class TreeEntryView(ApiModel):
    """One item of a directory listing."""

    name: str
    path: str
    type: str
    size: int | None


class FileView(ApiModel):
    """One file of the repository."""

    path: str
    size: int
    # Text files arrive decoded; binary ones only report their size.
    text: str | None
    binary: bool


class FileWrite(ApiModel):
    """A file to write through the console, and the commit that carries it."""

    content: str
    message: str = Field(min_length=1, max_length=COMMIT_MESSAGE_MAX_LENGTH)
    branch: str = Field(min_length=1, max_length=BRANCH_MAX_LENGTH)
    # Where the branch stood when the file was opened; None for a new branch.
    # An edit is refused when somebody else has moved it since.
    parent_commit: str | None = None


class CommitMade(ApiModel):
    """What a change made through the console came to."""

    commit: str
    branch: str
    path: str


class SearchMatchView(ApiModel):
    """One line of the repository that contains the phrase."""

    path: str
    line_number: int
    line: str


class CommitView(ApiModel):
    """One entry of the history."""

    hash: str
    author_name: str
    author_email: str
    authored_at: datetime
    subject: str


class TokenCreate(ApiModel):
    """A new access token for Git over HTTPS."""

    name: str = Field(min_length=1, max_length=TOKEN_NAME_MAX_LENGTH)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None


class TokenView(ApiModel):
    """A token as the console shows it; never its secret."""

    id: UUID
    name: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class NewTokenView(TokenView):
    """The same, plus the value, which is shown only once."""

    value: str


class SshKeyCreate(ApiModel):
    """A public key in the `ssh-ed25519 AAAA... comment` form."""

    name: str = Field(min_length=1, max_length=SSH_KEY_NAME_MAX_LENGTH)
    public_key: str = Field(min_length=1, max_length=SSH_KEY_MAX_LENGTH)


class SshKeyView(ApiModel):
    """A key as the console shows it; the fingerprint identifies it."""

    id: UUID
    name: str
    algorithm: str
    fingerprint: str
    created_at: datetime
    last_used_at: datetime | None


class ProtectedBranchCreate(ApiModel):
    """A branch name or a pattern such as `release/*`."""

    pattern: str = Field(min_length=1, max_length=BRANCH_PATTERN_MAX_LENGTH)


class ProtectedBranchView(ApiModel):
    """A protection rule as the console shows it."""

    id: UUID
    pattern: str
    created_at: datetime
