"""Argon2id password hashing helpers."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Hash a password with Argon2id; the result is suitable for database storage."""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a candidate password, returning False for mismatch or corrupt hashes."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def burn_password_hash(password: str) -> None:
    """Spend comparable Argon2 work for unknown-email login attempts."""
    _password_hasher.hash(password)
