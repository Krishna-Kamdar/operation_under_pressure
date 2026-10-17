import asyncio
import uuid

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionFactory
from app.models import (
    Membership,
    Priority,
    Role,
    Team,
    User,
    WorkItem,
    WorkItemStatus,
    WorkItemType,
)


async def seed() -> None:
    async with SessionFactory.begin() as session:
        if await session.scalar(select(User.id).limit(1)):
            return

        password_hash = hash_password("ChangeMe123!")
        users = [
            User(
                email="viewer@example.com",
                display_name="Vera Viewer",
                password_hash=password_hash,
            ),
            User(
                email="member@example.com",
                display_name="Mina Member",
                password_hash=password_hash,
            ),
            User(
                email="lead@example.com",
                display_name="Leo Lead",
                password_hash=password_hash,
            ),
            User(
                email="admin@example.com",
                display_name="Ada Admin",
                password_hash=password_hash,
            ),
        ]
        teams = [
            Team(name="Payments"),
            Team(name="Engineering"),
            Team(name="Compliance"),
        ]
        session.add_all([*users, *teams])
        await session.flush()

        session.add_all(
            [
                Membership(user_id=users[0].id, team_id=teams[0].id, role=Role.VIEWER),
                Membership(user_id=users[1].id, team_id=teams[0].id, role=Role.MEMBER),
                Membership(user_id=users[2].id, team_id=teams[0].id, role=Role.LEAD),
                Membership(user_id=users[3].id, team_id=teams[0].id, role=Role.ADMIN),
                Membership(user_id=users[2].id, team_id=teams[1].id, role=Role.MEMBER),
                Membership(user_id=users[3].id, team_id=teams[2].id, role=Role.ADMIN),
            ]
        )
        session.add(
            WorkItem(
                id=uuid.uuid4(),
                title="Investigate duplicate payment",
                description="Review the customer report and payment ledger.",
                item_type=WorkItemType.PAYMENT,
                priority=Priority.URGENT,
                status=WorkItemStatus.OPEN,
                team_id=teams[0].id,
                creator_id=users[1].id,
            )
        )


if __name__ == "__main__":
    asyncio.run(seed())
