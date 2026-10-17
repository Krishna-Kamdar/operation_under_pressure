from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authorize_team_action, get_current_user
from app.db import get_session
from app.item_schemas import (
    ActivityResponse,
    CommentCreate,
    CommentResponse,
    TransitionRequest,
    WorkItemCreate,
    WorkItemListResponse,
    WorkItemResponse,
    WorkItemUpdate,
)
from app.models import (
    ActivityEvent,
    ActivityEventType,
    Comment,
    IdempotencyKey,
    Membership,
    OutboxJob,
    OutboxStatus,
    Priority,
    Role,
    User,
    WorkItem,
    WorkItemStatus,
)

router = APIRouter(prefix="/items", tags=["work-items"])

MINIMUM_VIEW_ROLE = Role.VIEWER
MINIMUM_MUTATE_ROLE = Role.MEMBER


def _cursor_value(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp, item_id = decoded.split("|", maxsplit=1)
        return datetime.fromisoformat(timestamp), UUID(item_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor.") from exc


def _make_cursor(item: WorkItem) -> str:
    value = f"{item.updated_at.isoformat()}|{item.id}"
    return base64.urlsafe_b64encode(value.encode()).decode()


async def _load_authorized_item(
    session: AsyncSession, user: User, item_id: UUID, minimum_role: Role
) -> WorkItem:
    item = await session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    await authorize_team_action(session, user, item.team_id, minimum_role)
    return item


def _event(
    item_id: UUID, actor_id: UUID, event_type: ActivityEventType, payload: dict
) -> ActivityEvent:
    return ActivityEvent(
        work_item_id=item_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload,
    )


@router.get("", response_model=WorkItemListResponse)
async def list_items(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[WorkItemStatus | None, Query(alias="status")] = None,
    priority: Priority | None = None,
    assignee_id: UUID | None = None,
    team_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    assigned_to_me: bool = False,
    urgent: bool = False,
    awaiting_my_approval: bool = False,
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
) -> WorkItemListResponse:
    query = (
        select(WorkItem)
        .join(Membership, Membership.team_id == WorkItem.team_id)
        .where(Membership.user_id == user.id)
        .order_by(WorkItem.updated_at.desc(), WorkItem.id.desc())
    )
    if team_id is not None:
        query = query.where(WorkItem.team_id == team_id)
    if status_filter is not None:
        query = query.where(WorkItem.status == status_filter)
    if priority is not None:
        query = query.where(WorkItem.priority == priority)
    if assignee_id is not None:
        query = query.where(WorkItem.assignee_id == assignee_id)
    if assigned_to_me:
        query = query.where(WorkItem.assignee_id == user.id)
    if urgent:
        query = query.where(
            WorkItem.priority == Priority.URGENT,
            WorkItem.assignee_id.is_(None),
            WorkItem.status.notin_([WorkItemStatus.RESOLVED, WorkItemStatus.CLOSED]),
        )
    if awaiting_my_approval:
        # This queue is visible to every member of the item's team. The
        # transition endpoint separately enforces Lead/Admin approval.
        query = query.where(WorkItem.status == WorkItemStatus.AWAITING_APPROVAL)
    if q:
        term = f"%{q.strip()}%"
        query = query.where(
            or_(WorkItem.title.ilike(term), WorkItem.description.ilike(term))
        )
    parsed_cursor = _cursor_value(cursor)
    if parsed_cursor:
        timestamp, item_id = parsed_cursor
        query = query.where(
            or_(
                WorkItem.updated_at < timestamp,
                and_(WorkItem.updated_at == timestamp, WorkItem.id < item_id),
            )
        )
    rows = (await session.scalars(query.limit(limit + 1))).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    return WorkItemListResponse(
        items=items,
        next_cursor=_make_cursor(items[-1]) if has_more and items else None,
    )


@router.post("", response_model=WorkItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    request: WorkItemCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkItemResponse:
    await authorize_team_action(session, user, request.team_id, MINIMUM_MUTATE_ROLE)
    request_hash = hashlib.sha256(
        json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    await session.commit()
    async with session.begin():
        if idempotency_key:
            previous = await session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == user.id,
                    IdempotencyKey.operation == "create_item",
                    IdempotencyKey.key == idempotency_key,
                )
            )
            if previous:
                if previous.request_hash != request_hash:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency key was reused with different data.",
                    )
                return WorkItemResponse.model_validate(previous.response_body)
        item = WorkItem(
            title=request.title,
            description=request.description,
            item_type=request.item_type,
            priority=request.priority,
            status=WorkItemStatus.OPEN,
            team_id=request.team_id,
            creator_id=user.id,
            due_at=request.due_at,
        )
        session.add(item)
        await session.flush()
        session.add(
            _event(
                item.id,
                user.id,
                ActivityEventType.CREATED,
                {"status": item.status.value},
            )
        )
        response = WorkItemResponse.model_validate(item)
        if idempotency_key:
            session.add(
                IdempotencyKey(
                    user_id=user.id,
                    operation="create_item",
                    key=idempotency_key,
                    request_hash=request_hash,
                    response_status=201,
                    response_body=response.model_dump(mode="json"),
                )
            )
    return response


@router.get("/{item_id}", response_model=WorkItemResponse)
async def get_item(
    item_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkItemResponse:
    return await _load_authorized_item(session, user, item_id, MINIMUM_VIEW_ROLE)


@router.patch("/{item_id}", response_model=WorkItemResponse)
async def update_item(
    item_id: UUID,
    request: WorkItemUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkItemResponse:
    item = await _load_authorized_item(session, user, item_id, MINIMUM_MUTATE_ROLE)
    await session.commit()
    async with session.begin():
        values = request.model_dump(exclude={"expected_version"}, exclude_unset=True)
        if not values:
            return item
        result = await session.execute(
            update(WorkItem)
            .where(WorkItem.id == item_id, WorkItem.version == request.expected_version)
            .values(
                **values, version=WorkItem.version + 1, updated_at=datetime.now(UTC)
            )
            .returning(WorkItem)
        )
        updated = result.scalar_one_or_none()
        if updated is None:
            raise HTTPException(
                status_code=409, detail="This item changed; reload and try again."
            )
        for field, value in values.items():
            if field == "priority":
                event_type = ActivityEventType.PRIORITY_CHANGED
            else:
                event_type = ActivityEventType.UPDATED
            session.add(
                _event(
                    item_id, user.id, event_type, {"field": field, "value": str(value)}
                )
            )
    return updated


@router.post("/{item_id}/claim", response_model=WorkItemResponse)
async def claim_item(
    item_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkItemResponse:
    item = await _load_authorized_item(session, user, item_id, MINIMUM_MUTATE_ROLE)
    await session.commit()
    async with session.begin():
        result = await session.execute(
            update(WorkItem)
            .where(WorkItem.id == item.id, WorkItem.assignee_id.is_(None))
            .values(
                assignee_id=user.id,
                version=WorkItem.version + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(WorkItem)
        )
        claimed = result.scalar_one_or_none()
        if claimed is None:
            raise HTTPException(
                status_code=409, detail="This item has already been claimed."
            )
        session.add(
            _event(
                item.id,
                user.id,
                ActivityEventType.ASSIGNED,
                {"assignee_id": str(user.id)},
            )
        )
        session.add(
            OutboxJob(
                job_type="notify_assignee",
                payload={"work_item_id": str(item.id), "assignee_id": str(user.id)},
                status=OutboxStatus.PENDING,
            )
        )
    return claimed


@router.post("/{item_id}/unassign", response_model=WorkItemResponse)
async def unassign_item(
    item_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkItemResponse:
    item = await _load_authorized_item(session, user, item_id, MINIMUM_MUTATE_ROLE)
    membership = await authorize_team_action(
        session, user, item.team_id, MINIMUM_MUTATE_ROLE
    )
    if item.assignee_id is None:
        return item
    if item.assignee_id != user.id and membership.role not in {Role.LEAD, Role.ADMIN}:
        raise HTTPException(
            status_code=403,
            detail="Only the assignee, team Lead, or Admin may unassign this item.",
        )
    await session.commit()
    async with session.begin():
        result = await session.execute(
            update(WorkItem)
            .where(
                WorkItem.id == item.id,
                WorkItem.version == item.version,
                WorkItem.assignee_id.is_not(None),
            )
            .values(
                assignee_id=None,
                version=WorkItem.version + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(WorkItem)
        )
        unassigned = result.scalar_one_or_none()
        if unassigned is None:
            raise HTTPException(
                status_code=409, detail="This item changed; reload and try again."
            )
        session.add(
            _event(
                item.id,
                user.id,
                ActivityEventType.UNASSIGNED,
                {"assignee_id": None, "previous_assignee_id": str(item.assignee_id)},
            )
        )
    return unassigned


ALLOWED_TRANSITIONS: dict[WorkItemStatus, set[WorkItemStatus]] = {
    WorkItemStatus.OPEN: {WorkItemStatus.IN_PROGRESS},
    WorkItemStatus.IN_PROGRESS: {WorkItemStatus.AWAITING_APPROVAL},
    WorkItemStatus.AWAITING_APPROVAL: {WorkItemStatus.RESOLVED},
    WorkItemStatus.RESOLVED: {WorkItemStatus.CLOSED, WorkItemStatus.IN_PROGRESS},
    WorkItemStatus.CLOSED: {WorkItemStatus.IN_PROGRESS},
}


@router.post("/{item_id}/transition", response_model=WorkItemResponse)
async def transition_item(
    item_id: UUID,
    request: TransitionRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkItemResponse:
    item = await _load_authorized_item(session, user, item_id, MINIMUM_MUTATE_ROLE)
    membership = await authorize_team_action(
        session, user, item.team_id, MINIMUM_MUTATE_ROLE
    )
    if request.status not in ALLOWED_TRANSITIONS[item.status]:
        raise HTTPException(
            status_code=422,
            detail=f"Transition from {item.status.value} to {request.status.value} is not allowed.",
        )
    if item.status == WorkItemStatus.AWAITING_APPROVAL and membership.role not in {
        Role.LEAD,
        Role.ADMIN,
    }:
        raise HTTPException(
            status_code=403, detail="Only a team Lead or Admin may approve this item."
        )
    await session.commit()
    async with session.begin():
        result = await session.execute(
            update(WorkItem)
            .where(WorkItem.id == item.id, WorkItem.version == request.expected_version)
            .values(
                status=request.status,
                version=WorkItem.version + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(WorkItem)
        )
        transitioned = result.scalar_one_or_none()
        if transitioned is None:
            raise HTTPException(
                status_code=409, detail="This item changed; reload and try again."
            )
        session.add(
            _event(
                item.id,
                user.id,
                ActivityEventType.STATUS_CHANGED,
                {"from": item.status.value, "to": request.status.value},
            )
        )
    return transitioned


@router.get("/{item_id}/activity", response_model=list[ActivityResponse])
async def activity(
    item_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ActivityResponse]:
    await _load_authorized_item(session, user, item_id, MINIMUM_VIEW_ROLE)
    return list(
        (
            await session.scalars(
                select(ActivityEvent)
                .where(ActivityEvent.work_item_id == item_id)
                .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
                .limit(limit)
            )
        ).all()
    )


@router.post(
    "/{item_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    item_id: UUID,
    request: CommentCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommentResponse:
    item = await _load_authorized_item(session, user, item_id, MINIMUM_MUTATE_ROLE)
    await session.commit()
    async with session.begin():
        comment = Comment(work_item_id=item.id, author_id=user.id, body=request.body)
        session.add(comment)
        await session.flush()
        session.add(
            _event(
                item.id,
                user.id,
                ActivityEventType.COMMENTED,
                {"comment_id": str(comment.id)},
            )
        )
    return comment
