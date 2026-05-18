"""Authentication endpoints: login, profile, password change."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_session
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    """Exchange username + password for a JWT access token."""
    repo = UserRepository(session)
    user = await repo.get_by_username(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled"
        )
    token = create_access_token(user.username, is_admin=user.is_admin)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user."""
    return user


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Change the current user's password."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    user.password_hash = hash_password(body.new_password)
    await session.commit()
