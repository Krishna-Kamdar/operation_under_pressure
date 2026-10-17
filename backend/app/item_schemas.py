from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ActivityEventType, Priority, WorkItemStatus, WorkItemType


class WorkItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1)
    item_type: WorkItemType
    priority: Priority = Priority.MEDIUM
    team_id: UUID
    due_at: datetime | None = None


class WorkItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, min_length=1)
    item_type: WorkItemType | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    expected_version: int = Field(ge=1)


class WorkItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    item_type: WorkItemType
    priority: Priority
    status: WorkItemStatus
    team_id: UUID
    assignee_id: UUID | None
    creator_id: UUID
    due_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class WorkItemListResponse(BaseModel):
    items: list[WorkItemResponse]
    next_cursor: str | None


class TransitionRequest(BaseModel):
    status: WorkItemStatus
    expected_version: int = Field(ge=1)


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_item_id: UUID
    actor_id: UUID
    event_type: ActivityEventType
    payload: dict
    created_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Comment cannot be blank.")
        return value


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_item_id: UUID
    author_id: UUID
    body: str
    created_at: datetime
