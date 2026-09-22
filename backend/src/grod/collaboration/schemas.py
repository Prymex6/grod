"""Bodies of the member and issue endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from grod.accounts.schemas import ApiModel
from grod.collaboration.models import (
    BODY_MAX_LENGTH,
    BRANCH_MAX_LENGTH,
    PATH_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    IssueState,
    MergeState,
    QueueState,
)
from grod.repositories.models import LOGIN_REFERENCE_MAX_LENGTH, Role


class AuthorView(ApiModel):
    """Who wrote something, as little as the console needs."""

    login: str
    display_name: str


class MemberCreate(ApiModel):
    """Add somebody to a project, or change their role."""

    login: str = Field(min_length=1, max_length=LOGIN_REFERENCE_MAX_LENGTH)
    role: Role = Role.GUEST


class MemberView(ApiModel):
    """A member of a project."""

    login: str
    display_name: str
    role: Role
    created_at: datetime


class IssueCreate(ApiModel):
    """A new issue."""

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str = Field(default="", max_length=BODY_MAX_LENGTH)


class IssueUpdate(ApiModel):
    """Changing an issue; every field is optional."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=BODY_MAX_LENGTH)
    state: IssueState | None = None


class IssueView(ApiModel):
    """An issue as the console shows it."""

    id: UUID
    number: int
    title: str
    description: str
    state: IssueState
    author: AuthorView
    created_at: datetime
    updated_at: datetime | None
    closed_at: datetime | None


class CommentCreate(ApiModel):
    """A new comment under an issue."""

    body: str = Field(min_length=1, max_length=BODY_MAX_LENGTH)


class CommentView(ApiModel):
    """One entry of the discussion under an issue."""

    id: UUID
    body: str
    author: AuthorView
    created_at: datetime


class MergeRequestCreate(ApiModel):
    """A new merge request between two branches."""

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str = Field(default="", max_length=BODY_MAX_LENGTH)
    source_branch: str = Field(min_length=1, max_length=BRANCH_MAX_LENGTH)
    target_branch: str = Field(min_length=1, max_length=BRANCH_MAX_LENGTH)


class MergeRequestView(ApiModel):
    """A merge request as the console shows it."""

    id: UUID
    number: int
    title: str
    description: str
    state: MergeState
    source_branch: str
    target_branch: str
    merge_commit: str | None
    author: AuthorView
    created_at: datetime
    updated_at: datetime | None
    merged_at: datetime | None
    closed_at: datetime | None


class FileChangeView(ApiModel):
    """One file changed by a merge request."""

    path: str
    additions: int
    deletions: int
    binary: bool
    patch: str


class MergeCommitView(ApiModel):
    """One commit a merge request would bring in."""

    hash: str
    short_hash: str
    subject: str
    author_name: str
    authored_at: datetime


class ReviewCommentCreate(ApiModel):
    """A review comment, either general or pinned to one line."""

    body: str = Field(min_length=1, max_length=BODY_MAX_LENGTH)
    file_path: str | None = Field(default=None, max_length=PATH_MAX_LENGTH)
    line_number: int | None = Field(default=None, ge=1)


class ReviewCommentView(ApiModel):
    """One entry of the review discussion."""

    id: UUID
    body: str
    file_path: str | None
    line_number: int | None
    author: AuthorView
    created_at: datetime


class QueueEntryView(ApiModel):
    """Where one merge request stands in the line."""

    state: QueueState
    # 1 means next to go; 0 when the entry is no longer in line.
    position: int
    tested_commit: str
    pipeline_id: UUID | None
    last_error: str
    created_at: datetime


class QueuePlaceView(QueueEntryView):
    """One place in the queue, with the request standing there."""

    number: int
    title: str


class MergeRulesWrite(ApiModel):
    """What has to be true before anything of this project may be merged."""

    required_approvals: int = Field(default=0, ge=0, le=20)
    required_checks: list[str] = Field(default_factory=list, max_length=50)


class MergeRulesView(ApiModel):
    """The rules as they stand."""

    required_approvals: int
    required_checks: list[str]


class ApprovalView(ApiModel):
    """One person who said yes, and whether it still counts."""

    login: str
    display_name: str
    commit: str
    # An approval given on older work says nothing about the work now.
    stale: bool


class ApprovalStateView(ApiModel):
    """Whether a change has the yeses it needs."""

    given: list[ApprovalView]
    required: int
    counted: int
    missing_owners: list[str]
    satisfied: bool


class FindingView(ApiModel):
    """One remark a tool made about one line of the change."""

    path: str
    line: int
    column: int | None
    # The job that said it, which is how the console names the tool.
    tool: str
    message: str


class StackStepView(ApiModel):
    """One merge request of a stack, and where it stands in it."""

    number: int
    title: str
    state: MergeState
    source_branch: str
    target_branch: str
    # 1 is the bottom of the stack: the one that goes in first.
    position: int
