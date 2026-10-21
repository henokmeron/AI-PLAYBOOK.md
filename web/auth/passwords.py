"""Password hashing with stdlib scrypt (no plaintext storage)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# OWASP-oriented scrypt parameters for interactive login on a small console.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_MAX_PASSWORD_CHARS = 128
_MIN_PASSWORD_CHARS = 12


class PasswordError(ValueError):
    pass


def validate_password_policy(password: str) -> str:
    if not isinstance(password, str):
        raise PasswordError("password must be a string")
    if len(password) < _MIN_PASSWORD_CHARS or len(password) > _MAX_PASSWORD_CHARS:
        raise PasswordError(
            f"password must be between {_MIN_PASSWORD_CHARS} and {_MAX_PASSWORD_CHARS} characters"
        )
    if any(ord(ch) < 32 for ch in password):
        raise PasswordError("password must not contain control characters")
    return password


def hash_password(password: str) -> str:
    password = validate_password_policy(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_N,
        r=_R,
        p=_P,
        dklen=_DKLEN,
    )
    return "scrypt${n}${r}${p}${salt}${digest}".format(
        n=_N,
        r=_R,
        p=_P,
        salt=base64.urlsafe_b64encode(salt).decode("ascii"),
        digest=base64.urlsafe_b64encode(digest).decode("ascii"),
    )


# Used when the username is unknown so failed logins still pay one scrypt.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-operator-password")


def scrypt_hash_well_formed(encoded: str) -> bool:
    """True when the stored string is a bounded scrypt hash. The secret is not returned."""
    parts = _scrypt_parts(encoded)
    if parts is None:
        return False
    _n, _r, _p, salt, expected = parts
    return bool(salt) and bool(expected)


def _scrypt_parts(encoded: str) -> tuple[int, int, int, bytes, bytes] | None:
    if not isinstance(encoded, str):
        return None
    try:
        scheme, n_s, r_s, p_s, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "scrypt":
            return None
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return None
    if n < 2**12 or n > 2**20 or r < 1 or r > 16 or p < 1 or p > 4:
        return None
    return n, r, p, salt, expected


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    if len(password) > _MAX_PASSWORD_CHARS:
        return False
    parts = _scrypt_parts(encoded)
    if parts is None:
        return False
    n, r, p, salt, expected = parts
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected) or _DKLEN,
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)
