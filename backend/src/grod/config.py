"""Runtime configuration, read from environment variables prefixed with GROD_."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings of a single Grod instance."""

    model_config = SettingsConfigDict(env_prefix="GROD_", env_file=".env", extra="forbid")

    instance_name: str = "Gród"
    debug: bool = False
    database_url: PostgresDsn = PostgresDsn("postgresql+asyncpg://grod:grod@localhost:5433/grod")
    valkey_url: RedisDsn = RedisDsn("redis://localhost:6380/0")
    # The address applications use to reach the databases handed out to them;
    # empty means the same host the platform itself connects to.
    database_public_host: str = ""

    session_cookie_name: str = "grod_session"
    session_ttl_seconds: int = 14 * 24 * 3600
    # Cookies must stay plain HTTP while developing locally; production runs behind TLS.
    session_cookie_secure: bool = False
    pending_login_ttl_seconds: int = 5 * 60

    # Brute-force protection for the sign-in endpoint.
    login_attempt_limit: int = 10
    login_attempt_window_seconds: int = 15 * 60

    # Address this instance is reached at; it is also the OpenID Connect issuer.
    public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:5173/")
    oidc_private_key_path: Path = Path("var/oidc-private-key.pem")
    oauth_request_ttl_seconds: int = 10 * 60
    oauth_code_ttl_seconds: int = 60
    oauth_access_token_ttl_seconds: int = 60 * 60
    oauth_id_token_ttl_seconds: int = 60 * 60
    oauth_refresh_token_ttl_seconds: int = 30 * 24 * 3600

    # Passkeys belong to a domain; in development that is plain localhost.
    webauthn_rp_id: str = "localhost"

    # Outgoing email. The development stack runs Mailpit, which accepts
    # everything and shows it at http://localhost:8025 instead of sending it.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_use_tls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = "accounts@grod.local"
    password_reset_ttl_seconds: int = 30 * 60

    # Bare Git repositories live here, one folder per project.
    # Secrets of projects are encrypted with this key; it is created on first run.
    secret_key_path: Path = Path("var/secret-key")
    packages_path: Path = Path("var/packages")
    # What one account may hold before the platform says no. An account may
    # be given its own limits; these are what everybody starts with.
    quota_storage_bytes: int = 5 * 1024 * 1024 * 1024
    quota_buckets: int = 20
    quota_applications: int = 10
    quota_functions: int = 50
    quota_databases: int = 10
    quota_queues: int = 20
    quota_workspaces: int = 3
    # Container images: the blobs of every project, and the uploads in flight.
    registry_path: Path = Path("var/registry")
    # The files of every bucket live here, one folder per bucket.
    storage_path: Path = Path("var/storage")

    repositories_path: Path = Path("var/repositories")
    pages_path: Path = Path("var/pages")
    git_binary: str = "git"

    # Applications run as containers, each getting a port from this range
    # on the loopback address only.
    docker_binary: str = "docker"
    app_port_first: int = 14000
    app_port_last: int = 14999

    # Git over SSH. Port 22 needs privileges, so development uses 2222.
    ssh_host: str = "0.0.0.0"  # noqa: S104  (the Git endpoint must be reachable)
    ssh_port: int = 2222
    ssh_host_key_path: Path = Path("var/ssh-host-key")
    ssh_user: str = "git"


@lru_cache
def get_settings() -> Settings:
    """Return the instance settings, parsed once per process."""
    return Settings()
