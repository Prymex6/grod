"""Password hashing with Argon2id, the algorithm OWASP recommends."""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash that carries its own parameters and salt."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its hash without leaking the reason for failure."""
    try:
        return _hasher.verify(password_hash, password)
    except Argon2Error:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker parameters than the current ones."""
    return _hasher.check_needs_rehash(password_hash)
