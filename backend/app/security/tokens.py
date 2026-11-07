"""High-entropy opaque access-token helpers."""

import hashlib
import secrets


def create_access_token() -> tuple[str, str]:
    """Return a URL-safe 256-bit token and its SHA-256 database verifier."""
    token = secrets.token_urlsafe(32)
    return token, hash_access_token(token)


def hash_access_token(token: str) -> str:
    """Hash a bearer token before persisting or querying it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
