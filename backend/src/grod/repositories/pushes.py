"""What a push changed, so other modules can react to it.

Grod runs `git receive-pack` itself, over HTTPS and over SSH, so it compares
the branch tips before and after a push instead of installing a hook that
would have to call back into the platform.
"""

from grod.repositories import git
from grod.repositories.models import Project


async def branch_tips(project: Project) -> dict[str, str]:
    """Return the commit every branch points at right now."""
    refs = await git.list_refs(project.id, kind="heads")
    return {ref.name: ref.commit for ref in refs}


def moved_branches(before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
    """Return the branches a push created or moved, with their new commits."""
    return {name: commit for name, commit in after.items() if before.get(name) != commit}
