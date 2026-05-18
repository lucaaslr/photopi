"""Security primitives: password hashing (bcrypt) and JWT tokens (PyJWT).

Kept deliberately dependency-light: only `bcrypt` and `PyJWT`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


# --- Password hashing -----------------------------------------------------
def hash_password(plain: str) -> str:
    """Return a bcrypt hash for *plain*."""
    salt = bcrypt.gensalt(rounds=11)  # 11 rounds: secure but Pi-friendly
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification of *plain* against *hashed*."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- JSON Web Tokens ------------------------------------------------------
def create_access_token(subject: str, *, is_admin: bool = False) -> str:
    """Create a signed JWT for the given user *subject* (username)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Return the decoded payload, or None if the token is invalid/expired."""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
