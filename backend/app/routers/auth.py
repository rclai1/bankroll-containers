"""Password hashing and verification helpers."""

import base64
import hmac
import secrets

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_SALT_BYTES = 16
_KEY_BYTES = 32
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> dict[str, str]:
    """Hash a password with Scrypt and a fresh random salt.

    Store both returned strings. A new salt is generated for each password.
    """
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = Scrypt(
        salt=salt,
        length=_KEY_BYTES,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    ).derive(password.encode("utf-8"))
    return {
        "password_hash": base64.urlsafe_b64encode(digest).decode("ascii"),
        "password_salt": base64.urlsafe_b64encode(salt).decode("ascii"),
    }


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    """Check a password against the Scrypt hash and salt returned above."""
    if not all(isinstance(value, str) for value in (password, password_hash, password_salt)):
        raise TypeError("password, password_hash, and password_salt must be strings")
    try:
        salt = base64.urlsafe_b64decode(password_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(password_hash.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return False
    if len(salt) != _SALT_BYTES or len(expected) != _KEY_BYTES:
        return False
    actual = Scrypt(
        salt=salt,
        length=_KEY_BYTES,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    ).derive(password.encode("utf-8"))
    return hmac.compare_digest(actual, expected)


