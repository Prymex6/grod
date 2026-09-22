"""Time-based one-time codes from an authenticator app."""

import pyotp

# One step of tolerance on each side, so a code typed near the end of its
# 30-second window is still accepted.
VALID_WINDOW = 1


def generate_secret() -> str:
    """Return a new base32 secret for an authenticator app."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str, issuer: str) -> str:
    """Return the otpauth:// URI that authenticator apps read from a QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_code(secret: str, code: str) -> bool:
    """Check a six-digit code against the secret."""
    return pyotp.TOTP(secret).verify(code, valid_window=VALID_WINDOW)
