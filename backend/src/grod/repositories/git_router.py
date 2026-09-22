"""The Git endpoints a `git clone` or `git push` talks to.

They sit at the root of the instance, so a repository address looks like
https://grod.example/<login>/<project>.git — the shape Git users expect.
"""

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.repositories import after_push, git_http, pushes, service, tokens

router = APIRouter(tags=["repositories-git"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

BASIC_PREFIX = "Basic "
AUTHENTICATE_HEADER = {"WWW-Authenticate": 'Basic realm="Grod"'}
CREDENTIAL_PARTS = 2
SUFFIXES = ("/info/refs", "/git-upload-pack", "/git-receive-pack")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Sign in with an access token",
        headers=AUTHENTICATE_HEADER,
    )


async def _holder_from_basic_auth(
    db: AsyncSession, authorization: str | None
) -> tokens.TokenHolder | None:
    """Read the account out of a Basic header whose password is a token."""
    if authorization is None or not authorization.startswith(BASIC_PREFIX):
        return None
    try:
        decoded = base64.b64decode(authorization.removeprefix(BASIC_PREFIX)).decode()
    except binascii.Error, UnicodeDecodeError:
        return None
    parts = decoded.split(":", 1)
    if len(parts) != CREDENTIAL_PARTS:
        return None
    return await tokens.authenticate(db, parts[1])


def _may_use(holder: tokens.TokenHolder | None, *, writing: bool) -> User | None:
    if holder is None:
        return None
    needed = tokens.SCOPE_WRITE if writing else tokens.SCOPE_READ
    return holder.user if needed in holder.scopes else None


@router.api_route("/{owner}/{slug}.git{suffix:path}", methods=["GET", "POST"])
async def git_over_http(
    owner: str,
    slug: str,
    suffix: str,
    request: Request,
    db: DbSession,
    settings: SettingsDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Serve clone, fetch and push for one repository."""
    del settings
    if suffix not in SUFFIXES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unsupported Git endpoint")

    found = await service.find(db, owner_login=owner, slug=slug)
    body = await request.body()
    query_string = request.url.query
    wants_write = git_http.service_of(query_string, suffix) == git_http.RECEIVE_PACK

    holder = await _holder_from_basic_auth(db, authorization)
    user = _may_use(holder, writing=wants_write)

    access = (
        await service.access_of(db, project=found.project, user=user) if found is not None else None
    )

    # An unreadable project answers exactly like a missing one, except that a
    # caller without credentials is invited to send them.
    if found is None or access is None or not access.read:
        if user is None:
            raise _unauthorized()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such project")
    if wants_write and not access.write:
        if user is None:
            raise _unauthorized()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You may not push to this project")

    # The tips before the push tell the pipelines which branches it moved.
    before = await pushes.branch_tips(found.project) if wants_write else {}

    answer = await git_http.run_http_backend(
        project_id=found.project.id,
        suffix=suffix,
        method=request.method,
        query_string=query_string,
        content_type=request.headers.get("content-type", ""),
        body=body,
        remote_user=user.login if user else "",
    )

    if wants_write:
        await after_push.handle(db, project=found.project, before=before, pusher=user)
    return Response(content=answer.body, status_code=answer.status, headers=answer.headers)
