import asyncio
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg.errors import UniqueViolation
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import BusinessError
from app.models import User, UserSession
from app.repositories.user_repository import delete_session, find_session_user, find_user_by_email
from app.schemas.auth import UserResponse

_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class AuthenticatedSession:
    user: UserResponse
    token: str
    expires_at: datetime


def token_digest(token: str) -> str:
    """数据库只保存会话令牌的摘要。"""
    return hashlib.sha256(token.encode()).hexdigest()


async def _create_session(db: AsyncSession, user: User) -> AuthenticatedSession:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=get_settings().session_days)
    db.add(UserSession(token_hash=token_digest(token), user_id=user.id, expires_at=expires_at))
    await db.commit()
    return AuthenticatedSession(UserResponse(id=user.id, email=user.email), token, expires_at)


async def register(db: AsyncSession, email: str, password: str) -> AuthenticatedSession:
    """创建账号并建立登录会话。"""
    password_hash = await asyncio.to_thread(_password_hash.hash, password)
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        if (
            isinstance(error.orig, UniqueViolation)
            and error.orig.diag.constraint_name == "uq_users_email"
        ):
            raise BusinessError(409, "该邮箱已注册，请直接登录") from error
        raise
    return await _create_session(db, user)


async def login(db: AsyncSession, email: str, password: str) -> AuthenticatedSession:
    """校验密码并创建独立会话。"""
    user = await find_user_by_email(db, email)
    password_hash = user.password_hash if user is not None else _dummy_hash
    valid = await asyncio.to_thread(_password_hash.verify, password, password_hash)
    if not valid or user is None:
        raise BusinessError(401, "邮箱或密码不正确")
    return await _create_session(db, user)


async def current_user(db: AsyncSession, token: str | None) -> UserResponse:
    """校验会话令牌，登录状态以服务器记录为准。"""
    if token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        raise BusinessError(401, "请先登录")
    user = await find_session_user(db, token_digest(token))
    if user is None:
        raise BusinessError(401, "登录已过期，请重新登录")
    return UserResponse(id=user.id, email=user.email)


async def logout(db: AsyncSession, token: str | None) -> None:
    """注销当前设备的会话。"""
    if token is not None:
        await delete_session(db, token_digest(token))
        await db.commit()
