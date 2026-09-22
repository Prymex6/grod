"""Who has to say yes before a change goes in, and who already has.

Two rules can ask for a yes. The project can want a number of people, and the
repository can name owners of paths in a file — whoever touches those paths
needs a yes from one of them.
"""

import fnmatch
import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.models import User
from grod.collaboration.models import Approval, MergeRequest
from grod.repositories import git
from grod.repositories.models import Project

# Where the owners of paths are written. The first file found wins; the second
# name is there so a repository brought from elsewhere works without changes.
OWNERS_PATHS = (".grod/owners", "CODEOWNERS")
OWNER_RULE = re.compile(r"^(?P<pattern>\S+)\s+(?P<owners>.+)$")
MAX_DIFF_FILES = 500


class AlreadyApprovedError(Exception):
    """This account has already said yes to this request."""


class OwnApprovalError(Exception):
    """Whoever wrote the change may not be the one who approves it."""


@dataclass(frozen=True)
class OwnerRule:
    """One line of the owners file: a path pattern and who owns it."""

    pattern: str
    owners: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalView:
    """One yes, and whether it still counts."""

    login: str
    display_name: str
    commit: str
    stale: bool


@dataclass(frozen=True)
class ApprovalState:
    """Everything the console needs to say whether a change may go in."""

    given: list[ApprovalView] = field(default_factory=list)
    # How many people the project wants, and how many still count.
    required: int = 0
    counted: int = 0
    # Owners who have to say yes because of what the change touches.
    missing_owners: list[str] = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        """Whether every rule is met."""
        return self.counted >= self.required and not self.missing_owners


def parse_owners(text: str) -> list[OwnerRule]:
    """Read an owners file. Later lines win, the way such files usually work."""
    rules: list[OwnerRule] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        found = OWNER_RULE.match(line)
        if found is None:
            continue
        owners = tuple(
            owner.lstrip("@").lower() for owner in found.group("owners").split() if owner.strip()
        )
        if owners:
            rules.append(OwnerRule(pattern=found.group("pattern"), owners=owners))
    return rules


def owners_of(path: str, rules: list[OwnerRule]) -> tuple[str, ...]:
    """Who owns one path, by the last rule that matches it."""
    for rule in reversed(rules):
        if _matches(path, rule.pattern):
            return rule.owners
    return ()


def _matches(path: str, pattern: str) -> bool:
    """Whether a path falls under a pattern of the owners file."""
    if pattern in {"*", "**"}:
        return True
    if pattern.endswith("/"):
        return path.startswith(pattern.lstrip("/"))
    cleaned = pattern.lstrip("/")
    return fnmatch.fnmatch(path, cleaned) or path.startswith(f"{cleaned}/")


async def read_owners(project: Project, ref: str) -> list[OwnerRule]:
    """Read the owners file of a revision, if the repository has one."""
    for path in OWNERS_PATHS:
        try:
            raw = await git.read_blob(project.id, ref=ref, path=path)
        except git.PathNotFoundError, git.RefNotFoundError, git.GitError:
            continue
        return parse_owners(raw.decode("utf-8", errors="replace"))
    return []


async def approve(
    session: AsyncSession, *, merge_request: MergeRequest, user: User, commit: str
) -> Approval:
    """Say yes to a change, on the commit it stands at now."""
    if merge_request.author_id == user.id:
        raise OwnApprovalError

    approval = Approval(merge_request_id=merge_request.id, user_id=user.id, commit=commit)
    session.add(approval)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AlreadyApprovedError from error
    return approval


async def revoke(session: AsyncSession, *, merge_request: MergeRequest, user: User) -> bool:
    """Take a yes back. Returns whether there was one."""
    result = await session.execute(
        select(Approval).where(
            Approval.merge_request_id == merge_request.id, Approval.user_id == user.id
        )
    )
    found = result.scalar_one_or_none()
    if found is None:
        return False
    await session.delete(found)
    await session.commit()
    return True


async def _given(session: AsyncSession, merge_request: MergeRequest) -> list[tuple[Approval, User]]:
    result = await session.execute(
        select(Approval, User)
        .join(User, User.id == Approval.user_id)
        .where(Approval.merge_request_id == merge_request.id)
        .order_by(Approval.created_at)
    )
    return [(approval, user) for approval, user in result]


async def state_of(
    session: AsyncSession, *, project: Project, merge_request: MergeRequest
) -> ApprovalState:
    """Work out whether a change has the yeses it needs."""
    try:
        tip = await git.resolve_ref(project.id, merge_request.source_branch)
    except git.RefNotFoundError, git.GitError:
        tip = ""

    given: list[ApprovalView] = []
    fresh: set[str] = set()
    for approval, user in await _given(session, merge_request):
        # An approval given on older work no longer says anything about this one.
        stale = tip != "" and approval.commit != "" and approval.commit != tip
        given.append(
            ApprovalView(
                login=user.login,
                display_name=user.display_name,
                commit=approval.commit,
                stale=stale,
            )
        )
        if not stale:
            fresh.add(user.login)

    missing = await _missing_owners(
        session, project=project, merge_request=merge_request, approved_by=fresh
    )
    return ApprovalState(
        given=given,
        required=project.required_approvals,
        counted=len(fresh),
        missing_owners=missing,
    )


async def _missing_owners(
    session: AsyncSession,
    *,
    project: Project,
    merge_request: MergeRequest,
    approved_by: set[str],
) -> list[str]:
    """Owners of touched paths who have not said yes.

    Each rule that the change touches needs a yes from **one** of its owners,
    so a file owned by a pair does not need both of them.
    """
    rules = await read_owners(project, merge_request.target_branch)
    if not rules:
        return []

    try:
        changes = await git.diff(
            project.id,
            base=merge_request.target_branch,
            head=merge_request.source_branch,
            max_files=MAX_DIFF_FILES,
        )
    except git.RefNotFoundError, git.GitError:
        return []

    wanted: set[tuple[str, ...]] = set()
    for change in changes:
        owners = owners_of(change.path, rules)
        if owners:
            wanted.add(owners)

    missing: set[str] = set()
    for owners in wanted:
        if approved_by.isdisjoint(owners):
            missing.update(owners)

    # An owner who no longer has an account cannot be waited for.
    known: list[str] = []
    for login in sorted(missing):
        if await accounts.find_by_login(session, login) is not None:
            known.append(login)
    return known


async def forget_stale(session: AsyncSession, *, merge_request_id: UUID) -> None:
    """Remove every yes of one request; used when it is reopened."""
    result = await session.execute(
        select(Approval).where(Approval.merge_request_id == merge_request_id)
    )
    for approval in result.scalars():
        await session.delete(approval)
    await session.commit()
