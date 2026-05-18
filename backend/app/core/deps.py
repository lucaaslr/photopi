"""Reusable FastAPI dependencies (authentication / authorisation)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.database import get_session
from app.models.user import User
from app.repositories.user import UserRepository

# auto_error=False so we can support optional / guest access ourselves.
_bearer = HTTPBearer(auto_error=False)


async def _raw_token(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(None),
) -> str | None:
    """Extract raw JWT from Authorization header or ?token= query param.

    The query-param path exists so <img> and <video> tags (which cannot set
    custom headers) can still authenticate when loading media files.
    """
    if creds:
        return creds.credentials
    return token


async def get_current_user(
    raw: str | None = Depends(_raw_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated user or raise 401."""
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(raw)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    user = await UserRepository(session).get_by_username(payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown or inactive user"
        )
    return user


async def get_optional_user(
    raw: str | None = Depends(_raw_token),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Like get_current_user but returns None instead of raising.

    Used by endpoints that may be browsed by guests when ALLOW_GUEST is on.
    """
    if raw is None:
        return None
    payload = decode_token(raw)
    if not payload or "sub" not in payload:
        return None
    return await UserRepository(session).get_by_username(payload["sub"])


async def require_reader(
    user: User | None = Depends(get_optional_user),
) -> User | None:
    """Allow access if authenticated, or if guest browsing is enabled."""
    if user is None and not settings.allow_guest:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require an authenticated admin user."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user
