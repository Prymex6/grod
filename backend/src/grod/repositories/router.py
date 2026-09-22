"""Endpoints for projects, their contents and the access tokens."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.community import groups
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.repositories import (
    after_delete,
    after_push,
    git,
    pushes,
    service,
    ssh_keys,
    tokens,
    views,
)
from grod.repositories.schemas import (
    CommitMade,
    CommitView,
    FileView,
    FileWrite,
    NewTokenView,
    ProjectCreate,
    ProjectView,
    ProtectedBranchCreate,
    ProtectedBranchView,
    RefView,
    SearchMatchView,
    SshKeyCreate,
    SshKeyView,
    TokenCreate,
    TokenView,
    TreeEntryView,
)

router = APIRouter(tags=["repositories"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

MAX_COMMITS = 100
MAX_SEARCH_RESULTS = 200
MAX_TEXT_BYTES = 512 * 1024
OWNER_ACCESS = service.Access(read=True, write=True, manage=True, own=True)
# Explore only ever lists public projects, which a visitor may read and nothing more.
VISITOR_ACCESS = service.Access(read=True, write=False, manage=False, own=False)

NOT_FOUND_DETAIL = "No such project"
CANNOT_WRITE_DETAIL = "You may not write to this project"


async def _readable(
    db: AsyncSession, owner: str, slug: str, user: OptionalUser
) -> service.ProjectWithOwner:
    """Find a project the caller may read, or answer 404 either way."""
    found = await service.find(db, owner_login=owner, slug=slug)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    access = await service.access_of(db, project=found.project, user=user)
    # A private project must look exactly like one that does not exist.
    if not access.read:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return found


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate, db: DbSession, user: CurrentUser, settings: SettingsDependency
) -> ProjectView:
    """Create a project with an empty repository."""
    group = None
    if body.group is not None:
        group = await groups.find(db, body.group)
        role = None if group is None else await groups.role_of(db, group=group, user=user)
        if group is None or role is None or role not in groups.MANAGING_ROLES:
            # A group the caller may not fill looks the same as one that is not there.
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such group")

    try:
        project = await service.create(
            db,
            owner=user,
            slug=body.slug,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            group=group,
        )
    except service.SlugAlreadyUsedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="There is already a project at this address"
        ) from None
    except service.InvalidSlugError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid address") from None

    namespace = group.slug if group else user.login
    return await views.project_view(project, namespace, settings, OWNER_ACCESS)


@router.get("/projects")
async def list_projects(
    db: DbSession, user: CurrentUser, settings: SettingsDependency
) -> list[ProjectView]:
    """Return the projects of the signed-in account."""
    projects = await service.list_for_owner(db, owner=user)
    owned = [
        service.ProjectWithOwner(project=project, owner=user, namespace=user.login)
        for project in projects
    ]
    return await views.project_views(db, owned, user, settings, OWNER_ACCESS)


@router.get("/projects/explore")
async def explore_projects(
    db: DbSession,
    user: OptionalUser,
    settings: SettingsDependency,
    limit: Annotated[int, Query(le=50)] = 20,
) -> list[ProjectView]:
    """Return public projects, for visitors without an account too."""
    found = await service.list_public(db, limit=limit)
    return await views.project_views(db, found, user, settings, VISITOR_ACCESS)


@router.get("/projects/{owner}/{slug}")
async def read_project(
    owner: str, slug: str, db: DbSession, user: OptionalUser, settings: SettingsDependency
) -> ProjectView:
    """Return one project."""
    found = await _readable(db, owner, slug, user)
    access = await service.access_of(db, project=found.project, user=user)
    found_views = await views.project_views(db, [found], user, settings, access)
    return found_views[0]


@router.delete("/projects/{owner}/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(owner: str, slug: str, db: DbSession, user: CurrentUser) -> None:
    """Remove a project and its repository."""
    found = await _readable(db, owner, slug, user)
    access = await service.access_of(db, project=found.project, user=user)
    if not access.own:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the owner may delete a project")
    # The files go first: the rows still say where they are.
    await after_delete.handle(found.project.id)
    await service.delete(db, project=found.project)


@router.get("/projects/{owner}/{slug}/branches")
async def list_branches(owner: str, slug: str, db: DbSession, user: OptionalUser) -> list[RefView]:
    """Return the branches of a repository."""
    found = await _readable(db, owner, slug, user)
    refs = await git.list_refs(found.project.id, kind="heads")
    return [RefView(name=ref.name, commit=ref.commit) for ref in refs]


@router.get("/projects/{owner}/{slug}/tags")
async def list_tags(owner: str, slug: str, db: DbSession, user: OptionalUser) -> list[RefView]:
    """Return the tags of a repository."""
    found = await _readable(db, owner, slug, user)
    refs = await git.list_refs(found.project.id, kind="tags")
    return [RefView(name=ref.name, commit=ref.commit) for ref in refs]


@router.get("/projects/{owner}/{slug}/tree")
async def list_tree(
    owner: str,
    slug: str,
    db: DbSession,
    user: OptionalUser,
    ref: str | None = None,
    path: str = "",
) -> list[TreeEntryView]:
    """List one directory of a repository."""
    found = await _readable(db, owner, slug, user)
    try:
        entries = await git.list_tree(
            found.project.id, ref=ref or found.project.default_branch, path=path
        )
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such branch or commit") from None
    except git.PathNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such path") from None
    return [
        TreeEntryView(name=entry.name, path=entry.path, type=entry.type, size=entry.size)
        for entry in entries
    ]


@router.get("/projects/{owner}/{slug}/file")
async def read_file(
    owner: str,
    slug: str,
    path: str,
    db: DbSession,
    user: OptionalUser,
    ref: str | None = None,
) -> FileView:
    """Return one file of a repository, decoded when it is text."""
    found = await _readable(db, owner, slug, user)
    revision = ref or found.project.default_branch
    try:
        size = await git.blob_size(found.project.id, ref=revision, path=path)
        if size > MAX_TEXT_BYTES:
            return FileView(path=path, size=size, text=None, binary=True)
        content = await git.read_blob(found.project.id, ref=revision, path=path)
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such branch or commit") from None
    except git.PathNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such file") from None

    try:
        return FileView(path=path, size=size, text=content.decode(), binary=False)
    except UnicodeDecodeError:
        return FileView(path=path, size=size, text=None, binary=True)


@router.get("/projects/{owner}/{slug}/search")
async def search_repository(
    owner: str,
    slug: str,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    db: DbSession,
    user: OptionalUser,
    ref: str | None = None,
    limit: Annotated[int, Query(le=MAX_SEARCH_RESULTS)] = 50,
) -> list[SearchMatchView]:
    """Find a phrase in the files of a repository."""
    found = await _readable(db, owner, slug, user)
    try:
        matches = await git.search(
            found.project.id,
            ref=ref or found.project.default_branch,
            query=q,
            limit=limit,
        )
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such branch or commit") from None
    return [
        SearchMatchView(path=match.path, line_number=match.line_number, line=match.line)
        for match in matches
    ]


@router.get("/projects/{owner}/{slug}/commits")
async def list_commits(
    owner: str,
    slug: str,
    db: DbSession,
    user: OptionalUser,
    ref: str | None = None,
    path: str | None = None,
    limit: Annotated[int, Query(le=MAX_COMMITS)] = 30,
    skip: int = 0,
) -> list[CommitView]:
    """Return the history of a branch."""
    found = await _readable(db, owner, slug, user)
    try:
        commits = await git.list_commits(
            found.project.id,
            ref=ref or found.project.default_branch,
            limit=limit,
            skip=skip,
            path=path,
        )
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such branch or commit") from None
    return [
        CommitView(
            hash=commit.hash,
            author_name=commit.author_name,
            author_email=commit.author_email,
            authored_at=commit.authored_at,
            subject=commit.subject,
        )
        for commit in commits
    ]


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenCreate, db: DbSession, user: CurrentUser) -> NewTokenView:
    """Create an access token for Git over HTTPS."""
    try:
        created = await tokens.create(
            db, user=user, name=body.name, scopes=body.scopes, expires_at=body.expires_at
        )
    except tokens.UnsupportedScopeError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Supported scopes: {', '.join(tokens.SUPPORTED_SCOPES)}",
        ) from None
    return NewTokenView.model_validate(
        {
            "id": created.token.id,
            "name": created.token.name,
            "scopes": created.token.scopes,
            "created_at": created.token.created_at,
            "expires_at": created.token.expires_at,
            "last_used_at": created.token.last_used_at,
            "value": created.value,
        }
    )


@router.get("/tokens")
async def list_tokens(db: DbSession, user: CurrentUser) -> list[TokenView]:
    """Return the access tokens of the signed-in account."""
    return [TokenView.model_validate(token) for token in await tokens.list_for(db, user=user)]


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(token_id: UUID, db: DbSession, user: CurrentUser) -> None:
    """Remove one access token."""
    if not await tokens.delete(db, user=user, token_id=token_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown token")


def _clean_path(path: str) -> str:
    """Refuse a path that would step outside the repository."""
    cleaned = path.strip("/")
    parts = cleaned.split("/")
    if not cleaned or "" in parts or ".." in parts or ".git" in parts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid path")
    return cleaned


async def _commit(
    db: AsyncSession,
    found: service.ProjectWithOwner,
    user: CurrentUser,
    *,
    edit: git.FileEdit,
    message: str,
    branch: str,
    parent: str | None,
) -> CommitMade:
    """Write one change into a branch and tell the platform it happened.

    A change made in the console has to set the same things going as a push
    from a terminal, so it goes through the same fan-out.
    """
    access = await service.access_of(db, project=found.project, user=user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=CANNOT_WRITE_DETAIL)

    before = await pushes.branch_tips(found.project)
    try:
        commit = await git.commit_files(
            found.project.id,
            branch=branch,
            edits=[edit],
            message=message,
            author_name=user.display_name,
            author_email=user.email,
            parent=parent,
        )
    except git.StaleBranchError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Somebody changed this branch in the meantime"
        ) from None
    except git.GitError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None

    await after_push.handle(db, project=found.project, before=before, pusher=user)
    return CommitMade(commit=commit, branch=branch, path=edit.path)


@router.put("/projects/{owner}/{slug}/files/{path:path}")
async def write_file(
    owner: str, slug: str, path: str, body: FileWrite, db: DbSession, user: CurrentUser
) -> CommitMade:
    """Write a file into a branch, making the commit that carries it."""
    found = await _readable(db, owner, slug, user)
    cleaned = _clean_path(path)
    return await _commit(
        db,
        found,
        user,
        edit=git.FileEdit(path=cleaned, content=body.content.encode()),
        message=body.message,
        branch=body.branch,
        parent=body.parent_commit,
    )


@router.delete("/projects/{owner}/{slug}/files/{path:path}")
async def delete_file(
    owner: str,
    slug: str,
    path: str,
    db: DbSession,
    user: CurrentUser,
    branch: str,
    message: str,
    # Query parameters are spelled the way the JSON is, not the way Python is.
    parent_commit: Annotated[str | None, Query(alias="parentCommit")] = None,
) -> CommitMade:
    """Take a file out of a branch, making the commit that does it."""
    found = await _readable(db, owner, slug, user)
    cleaned = _clean_path(path)
    try:
        await git.blob_size(found.project.id, ref=branch, path=cleaned)
    except git.PathNotFoundError, git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such file") from None

    return await _commit(
        db,
        found,
        user,
        edit=git.FileEdit(path=cleaned, content=None),
        message=message,
        branch=branch,
        parent=parent_commit,
    )


async def _writable(
    db: AsyncSession, owner: str, slug: str, user: CurrentUser
) -> service.ProjectWithOwner:
    """Find a project whose settings the caller may change."""
    found = await _readable(db, owner, slug, user)
    access = await service.access_of(db, project=found.project, user=user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only a maintainer may do this")
    return found


@router.get("/projects/{owner}/{slug}/protected-branches")
async def list_protected_branches(
    owner: str, slug: str, db: DbSession, user: OptionalUser
) -> list[ProtectedBranchView]:
    """Return the protection rules of a project."""
    found = await _readable(db, owner, slug, user)
    rules = await service.list_protected_branches(db, project=found.project)
    return [ProtectedBranchView.model_validate(rule) for rule in rules]


@router.post("/projects/{owner}/{slug}/protected-branches", status_code=status.HTTP_201_CREATED)
async def protect_branch(
    owner: str,
    slug: str,
    body: ProtectedBranchCreate,
    db: DbSession,
    user: CurrentUser,
) -> ProtectedBranchView:
    """Protect branches matching a pattern against deletion and rewriting."""
    found = await _writable(db, owner, slug, user)
    try:
        rule = await service.protect_branch(db, project=found.project, pattern=body.pattern)
    except service.PatternAlreadyProtectedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This pattern is already protected"
        ) from None
    return ProtectedBranchView.model_validate(rule)


@router.delete(
    "/projects/{owner}/{slug}/protected-branches/{pattern:path}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unprotect_branch(
    owner: str, slug: str, pattern: str, db: DbSession, user: CurrentUser
) -> None:
    """Drop one protection rule."""
    found = await _writable(db, owner, slug, user)
    if not await service.unprotect_branch(db, project=found.project, pattern=pattern):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such rule")


@router.post("/ssh-keys", status_code=status.HTTP_201_CREATED)
async def add_ssh_key(body: SshKeyCreate, db: DbSession, user: CurrentUser) -> SshKeyView:
    """Register a public key, so Git may reach the repositories over SSH."""
    try:
        key = await ssh_keys.add(db, user=user, name=body.name, text=body.public_key)
    except ssh_keys.InvalidKeyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="This is not an OpenSSH public key"
        ) from None
    except ssh_keys.KeyAlreadyAddedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This key is already registered"
        ) from None
    return SshKeyView.model_validate(key)


@router.get("/ssh-keys")
async def list_ssh_keys(db: DbSession, user: CurrentUser) -> list[SshKeyView]:
    """Return the public keys of the signed-in account."""
    keys = await ssh_keys.list_for(db, user=user)
    return [SshKeyView.model_validate(key) for key in keys]


@router.delete("/ssh-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ssh_key(key_id: UUID, db: DbSession, user: CurrentUser) -> None:
    """Remove one public key."""
    if not await ssh_keys.delete(db, user=user, key_id=key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown key")


@router.put("/projects/{owner}/{slug}/star", status_code=status.HTTP_204_NO_CONTENT)
async def star_project(owner: str, slug: str, db: DbSession, user: CurrentUser) -> None:
    """Star a project. Anybody who may read it may star it."""
    found = await _readable(db, owner, slug, user)
    await service.star(db, project=found.project, user=user)


@router.delete("/projects/{owner}/{slug}/star", status_code=status.HTTP_204_NO_CONTENT)
async def unstar_project(owner: str, slug: str, db: DbSession, user: CurrentUser) -> None:
    """Take a star back."""
    found = await _readable(db, owner, slug, user)
    if not await service.unstar(db, project=found.project, user=user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You have not starred this project")


@router.get("/starred")
async def list_starred_projects(
    db: DbSession, user: CurrentUser, settings: SettingsDependency
) -> list[ProjectView]:
    """Return the projects the signed-in account starred."""
    found = await service.list_starred(db, user=user)
    return await views.project_views(db, found, user, settings, None)
