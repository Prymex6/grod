"""The RSA key pair that signs OpenID Connect tokens."""

from functools import lru_cache
from typing import Any

from joserfc.jwk import RSAKey

from grod.config import get_settings

KEY_SIZE = 2048
SIGNING_ALGORITHM = "RS256"


@lru_cache
def get_signing_key() -> RSAKey:
    """Load the signing key, creating it on first run.

    The key never leaves this instance and is kept outside the repository.
    """
    path = get_settings().oidc_private_key_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(RSAKey.generate_key(KEY_SIZE).as_pem(private=True))
        path.chmod(0o600)
    return RSAKey.import_key(path.read_bytes())


def get_key_id() -> str:
    """Identifier of the current signing key, published in the JWKS."""
    return get_signing_key().thumbprint()


def get_public_jwks() -> dict[str, Any]:
    """Public half of the key set, so clients can verify our tokens."""
    public_key: dict[str, Any] = dict(get_signing_key().as_dict(private=False))
    public_key.update({"kid": get_key_id(), "use": "sig", "alg": SIGNING_ALGORITHM})
    return {"keys": [public_key]}
