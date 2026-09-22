"""Encrypting the secrets a project keeps.

The instance has one key, created on first use and kept next to the other data
of the instance. Nothing in the database is readable without that file.
"""

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from grod.config import get_settings

KEY_MODE = 0o600


class UnreadableSecretError(Exception):
    """The value cannot be decrypted with the key this instance has."""


def _load_or_create_key(path: Path) -> bytes:
    """Return the key of the instance, creating it on first run."""
    if path.exists():
        return path.read_bytes().strip()

    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    # The key is as good as every secret it protects.
    path.chmod(KEY_MODE)
    return key


@lru_cache
def _cipher() -> Fernet:
    return Fernet(_load_or_create_key(get_settings().secret_key_path))


def encrypt(value: str) -> str:
    """Turn a secret into the form that is kept in the database."""
    return _cipher().encrypt(value.encode()).decode()


def decrypt(stored: str) -> str:
    """Read a secret back; raises when the key does not match."""
    try:
        return _cipher().decrypt(stored.encode()).decode()
    except InvalidToken as error:
        raise UnreadableSecretError from error
