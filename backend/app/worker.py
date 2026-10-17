from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxJob, OutboxStatus

JobHandler = Callable[[dict], Awaitable[None]]


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** max(attempts - 1, 0)))


async def claim_next_job(session: AsyncSession) -> OutboxJob | None:
    result = await session.execute(
        select(OutboxJob)
        .where(
            OutboxJob.status == OutboxStatus.PENDING,
            OutboxJob.next_attempt_at <= datetime.now(UTC),
        )
        .order_by(OutboxJob.created_at, OutboxJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = OutboxStatus.PROCESSING
    job.attempts += 1
    await session.commit()
    return job


async def process_job(
    session: AsyncSession,
    job: OutboxJob,
    handlers: dict[str, JobHandler],
) -> None:
    if job.status == OutboxStatus.COMPLETED:
        return
    handler = handlers.get(job.job_type)
    if handler is None:
        job.status = OutboxStatus.FAILED
        job.last_error = f"No handler registered for job type: {job.job_type}"
        await session.commit()
        return
    try:
        await handler(job.payload)
    except Exception as exc:
        job.last_error = str(exc)
        if job.attempts >= job.max_attempts:
            job.status = OutboxStatus.FAILED
        else:
            job.status = OutboxStatus.PENDING
            job.next_attempt_at = datetime.now(UTC) + retry_delay(job.attempts)
        await session.commit()
        raise
    job.status = OutboxStatus.COMPLETED
    job.processed_at = datetime.now(UTC)
    await session.commit()


async def notify_assignee(payload: dict) -> None:
    # The assessment does not require a real email provider. The durable job
    # state still demonstrates retry and idempotent processing semantics.
    if not UUID(payload["work_item_id"]) or not UUID(payload["assignee_id"]):
        raise ValueError("Notification payload contains invalid identifiers.")
