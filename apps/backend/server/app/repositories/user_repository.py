from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserSession


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    """按规范化邮箱查找账号。"""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().one_or_none()


async def find_session_user(db: AsyncSession, token_hash: str) -> User | None:
    """只返回尚未过期、尚未注销的会话所属用户。"""
    result = await db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    return result.scalars().one_or_none()


async def delete_session(db: AsyncSession, token_hash: str) -> None:
    """撤销指定会话，不影响其他设备。"""
    await db.execute(delete(UserSession).where(UserSession.token_hash == token_hash))
