"""Looking through a repository for secrets, and keeping what was found.

A scan reads the tree of one revision whole rather than the change that came
in, so the list of findings is always what the repository holds now: a secret
that arrives through a merge is seen, and one that is taken out closes itself.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.repositories import git
from grod.repositories.models import Project
from grod.scanning import rules
from grod.scanning.models import SNIPPET_MAX_LENGTH, Finding, FindingState

MAX_FILES = 2000
MAX_FILE_BYTES = 512 * 1024
# Enough of the secret to recognise it, never enough to use it.
SHOWN_CHARACTERS = 4
MASK = "…"


@dataclass(frozen=True)
class Hit:
    """One match, before it is written down."""

    rule: str
    path: str
    line: int
    snippet: str
    fingerprint: str


@dataclass(frozen=True)
class ScanResult:
    """What one scan changed."""

    commit: str
    files: int
    opened: int
    closed: int
    open_total: int


def fingerprint(secret: str) -> str:
    """The name a secret is known by here, which is not the secret."""
    return hashlib.sha256(secret.encode()).hexdigest()


def mask(line: str, secret: str) -> str:
    """The line with the secret starred out, cut to something readable."""
    head = secret[:SHOWN_CHARACTERS]
    hidden = f"{head}{MASK}" if len(secret) > SHOWN_CHARACTERS else MASK
    return line.replace(secret, hidden).strip()[:SNIPPET_MAX_LENGTH]


def scan_text(text: str, *, path: str) -> list[Hit]:
    """Every secret one file holds."""
    hits: list[Hit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if rules.excused(line):
            continue
        for rule in rules.RULES:
            found = rule.pattern.search(line)
            if found is None:
                continue
            # A rule may point at the part worth hiding; otherwise all of it is.
            secret = found.groupdict().get("secret") or found.group(0)
            shown = mask(line, secret) if rule.masked else line.strip()[:SNIPPET_MAX_LENGTH]
            hits.append(
                Hit(
                    rule=rule.name,
                    path=path,
                    line=number,
                    snippet=shown,
                    fingerprint=fingerprint(secret),
                )
            )
    return hits


def _readable(raw: bytes) -> str | None:
    """The text of a file, or None when it is not text at all."""
    if b"\0" in raw[:1024]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


async def _look(project: Project, ref: str) -> tuple[str, list[Hit], int]:
    """Read the tree of a revision and collect every secret in it."""
    commit = await git.resolve_ref(project.id, ref)
    files = await git.list_files(project.id, ref=commit, limit=MAX_FILES)

    hits: list[Hit] = []
    looked = 0
    for entry in files:
        if rules.skipped(entry.path) or (entry.size or 0) > MAX_FILE_BYTES:
            continue
        raw = await git.read_blob(project.id, ref=commit, path=entry.path)
        text = _readable(raw)
        if text is None:
            continue
        looked += 1
        hits += scan_text(text, path=entry.path)
    return commit, hits, looked


async def scan(session: AsyncSession, *, project: Project, ref: str | None = None) -> ScanResult:
    """Look through one revision and bring the findings of a project up to date."""
    branch = ref or project.default_branch
    commit, hits, looked = await _look(project, branch)
    now = datetime.now(UTC)

    known = {
        (finding.rule, finding.path, finding.fingerprint): finding
        for finding in await list_findings(session, project=project)
    }

    opened = 0
    for hit in hits:
        finding = known.get((hit.rule, hit.path, hit.fingerprint))
        if finding is None:
            session.add(
                Finding(
                    project_id=project.id,
                    rule=hit.rule,
                    path=hit.path,
                    line=hit.line,
                    snippet=hit.snippet,
                    fingerprint=hit.fingerprint,
                    commit=commit,
                    state=FindingState.OPEN,
                    last_seen_at=now,
                )
            )
            opened += 1
            continue

        finding.line = hit.line
        finding.snippet = hit.snippet
        finding.commit = commit
        finding.last_seen_at = now
        # Somebody who looked and said it is fine is not asked again.
        if finding.state == FindingState.FIXED:
            finding.state = FindingState.OPEN

    # Anything the scan did not meet again is no longer in the repository.
    seen = {(hit.rule, hit.path, hit.fingerprint) for hit in hits}
    closed = 0
    for address, finding in known.items():
        if address not in seen and finding.state == FindingState.OPEN:
            finding.state = FindingState.FIXED
            closed += 1

    try:
        await session.commit()
    except IntegrityError:
        # Two scans of the same push crossed; the first one wrote the rows.
        await session.rollback()

    still_open = await count_open(session, project_id=project.id)
    return ScanResult(
        commit=commit, files=looked, opened=opened, closed=closed, open_total=still_open
    )


async def list_findings(
    session: AsyncSession, *, project: Project, state: FindingState | None = None
) -> list[Finding]:
    """Return what a project holds, the newest first."""
    query = select(Finding).where(Finding.project_id == project.id)
    if state is not None:
        query = query.where(Finding.state == state)
    result = await session.execute(query.order_by(Finding.created_at.desc()))
    return list(result.scalars())


async def count_open(session: AsyncSession, *, project_id: UUID) -> int:
    """How many findings still wait for somebody to deal with them."""
    result = await session.execute(
        select(Finding.id).where(
            Finding.project_id == project_id, Finding.state == FindingState.OPEN
        )
    )
    return len(list(result.scalars()))


async def find(session: AsyncSession, *, project: Project, finding_id: UUID) -> Finding | None:
    """Return one finding of a project."""
    finding = await session.get(Finding, finding_id)
    if finding is None or finding.project_id != project.id:
        return None
    return finding


async def set_state(session: AsyncSession, *, finding: Finding, state: FindingState) -> Finding:
    """Say what was decided about a finding."""
    finding.state = state
    await session.commit()
    return finding
