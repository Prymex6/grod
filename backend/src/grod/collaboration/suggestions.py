"""Turning a suggestion written in a review into a commit.

A reviewer writes what the line should say instead, inside a fenced block
marked `suggestion`. Whoever may push can then take it with one click, and
the platform writes the commit — nobody copies text by hand.
"""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.collaboration.models import MergeRequest, MergeRequestComment
from grod.repositories import git
from grod.repositories.models import Project

# The same fence GitHub and GitLab use, so a habit brought from there works.
BLOCK_RULE = re.compile(r"```suggestion[^\n]*\n(?P<body>.*?)```", re.DOTALL)
MAX_FILE_BYTES = 1024 * 1024


class NoSuggestionError(Exception):
    """The comment does not carry a suggestion."""


class NotOnALineError(Exception):
    """The comment is not attached to a line of a file."""


class LineIsGoneError(Exception):
    """The file no longer has that line; the suggestion is out of date."""


def read_suggestion(body: str) -> str | None:
    """The replacement text a comment carries, if it carries one."""
    found = BLOCK_RULE.search(body)
    if found is None:
        return None
    # The fence itself adds one newline; the text may be empty on purpose,
    # which is how a suggestion says "take this line out".
    return found.group("body").removesuffix("\n")


async def apply(
    session: AsyncSession,
    *,
    project: Project,
    merge_request: MergeRequest,
    comment: MergeRequestComment,
    user: User,
) -> str:
    """Write the suggestion into the source branch and return the commit."""
    del session
    if comment.file_path is None or comment.line_number is None:
        raise NotOnALineError

    replacement = read_suggestion(comment.body)
    if replacement is None:
        raise NoSuggestionError

    branch = merge_request.source_branch
    tip = await git.resolve_ref(project.id, branch)
    raw = await git.read_blob(project.id, ref=tip, path=comment.file_path)
    if len(raw) > MAX_FILE_BYTES:
        raise LineIsGoneError(comment.file_path)

    text = raw.decode("utf-8")
    lines = text.split("\n")
    index = comment.line_number - 1
    if index < 0 or index >= len(lines):
        raise LineIsGoneError(comment.file_path)

    lines[index : index + 1] = replacement.split("\n") if replacement else []
    return await git.commit_files(
        project.id,
        branch=branch,
        edits=[git.FileEdit(path=comment.file_path, content="\n".join(lines).encode())],
        message=f"Apply suggestion to {comment.file_path}:{comment.line_number}",
        author_name=user.display_name,
        author_email=user.email,
        parent=tip,
    )
