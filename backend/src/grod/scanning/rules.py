"""What a secret left in code looks like.

One place holds every pattern, so adding a rule never means touching the
scanner, and a rule that turns out to be noisy can be taken out again without
looking anywhere else.
"""

import re
from dataclasses import dataclass

# A line that says so is left alone, the way linters let a line be excused.
IGNORE_MARK = "scanning:ignore"

# Words that give a placeholder away, so an example in a README is not a leak.
PLACEHOLDERS = (
    "changeme",
    "example",
    "placeholder",
    "your-",
    "twoj",
    "xxxx",
    "****",
    "...",
    "<",
    "${",
    "{{",
)


@dataclass(frozen=True)
class Rule:
    """One kind of secret, and how to spot it."""

    name: str
    pattern: re.Pattern[str]
    # A rule that catches anything shaped like a password is worth having but
    # is wrong more often, so the console can say which findings to trust.
    certain: bool = True
    # Some matches are only a marker — the line that opens a private key holds
    # no secret of its own — and starring those out would hide nothing and
    # leave the finding unreadable.
    masked: bool = True

    # A pattern may name the group "secret" when only part of what it matched
    # is worth hiding, so the name of the setting still shows.


RULES: tuple[Rule, ...] = (
    Rule(
        name="private-key",
        pattern=re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
        masked=False,
    ),
    Rule(name="aws-access-key", pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    Rule(
        name="github-token",
        pattern=re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})\b"),
    ),
    Rule(name="gitlab-token", pattern=re.compile(r"\bglpat-[A-Za-z0-9_-]{20}\b")),
    Rule(name="slack-token", pattern=re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    Rule(name="google-api-key", pattern=re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    Rule(name="stripe-key", pattern=re.compile(r"\b[sr]k_live_[0-9A-Za-z]{10,}\b")),
    Rule(name="openai-key", pattern=re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    # The platform hands out tokens of its own, and they leak the same way.
    Rule(
        name="grod-token",
        pattern=re.compile(r"\bgrod(?:run|czuj|srv)?_[0-9a-f]{32}_[A-Za-z0-9_-]{20,}\b"),
    ),
    Rule(
        name="jwt",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    # A connection string carrying its own password.
    Rule(
        name="database-url",
        pattern=re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]+:"
            r"(?P<secret>[^\s:@/]{4,})@"
        ),
    ),
    Rule(
        name="password-in-code",
        pattern=re.compile(
            r"(?i)\b(?:password|passwd|hasl[oa]|secret|api[_-]?key|token)\s*[:=]\s*"
            r"[\"'](?P<secret>[^\"'\s]{8,})[\"']"
        ),
        certain=False,
    ),
)

# Files that are generated or vendored: scanning them finds other people's
# noise, never a secret the author of this repository put there.
SKIPPED_PATHS = (
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    ".venv/",
    "__pycache__/",
)
SKIPPED_SUFFIXES = (
    ".lock",
    ".min.js",
    ".min.css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp4",
    ".mp3",
)
SKIPPED_NAMES = ("package-lock.json", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock")


def skipped(path: str) -> bool:
    """Whether a file is not worth looking at."""
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    return (
        any(part in lowered for part in SKIPPED_PATHS)
        or lowered.endswith(SKIPPED_SUFFIXES)
        or name in {skipped.lower() for skipped in SKIPPED_NAMES}
    )


def excused(line: str) -> bool:
    """Whether the line asks to be left alone, or is plainly an example."""
    lowered = line.lower()
    return IGNORE_MARK in lowered or any(word in lowered for word in PLACEHOLDERS)


def is_certain(name: str) -> bool:
    """Whether a rule of that name is one to trust without looking twice."""
    return all(rule.certain for rule in RULES if rule.name == name)
