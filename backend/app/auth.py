import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Membership, Role, User

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = password_hash.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode(),
            base64.urlsafe_b64decode(salt.encode()),
            int(iterations),
        )
        return hmac.compare_digest(
            base64.urlsafe_b64decode(expected.encode()),
            actual,
        )
    except (TypeError, ValueError):
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    expires_at = datetime.now(UTC) + timedelta(hours=8)
    payload = {"sub": str(user_id), "exp": expires_at}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise unauthorized from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


async def get_membership(
    session: AsyncSession, user_id: uuid.UUID, team_id: uuid.UUID
) -> Membership | None:
    return await session.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.team_id == team_id,
        )
    )


ROLE_RANK = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.LEAD: 2,
    Role.ADMIN: 3,
}


def require_team_role(membership: Membership | None, minimum_role: Role) -> Membership:
    if membership is None or ROLE_RANK[membership.role] < ROLE_RANK[minimum_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action for this team.",
        )
    return membership


async def authorize_team_action(
    session: AsyncSession,
    user: User,
    team_id: uuid.UUID,
    minimum_role: Role,
) -> Membership:
    membership = await get_membership(session, user.id, team_id)
    return require_team_role(membership, minimum_role)
