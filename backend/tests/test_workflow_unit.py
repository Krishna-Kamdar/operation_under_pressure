from app.models import ActivityEventType, WorkItemStatus
from app.routers.items import ALLOWED_TRANSITIONS


def test_workflow_rejects_direct_open_to_closed_transition() -> None:
    assert WorkItemStatus.CLOSED not in ALLOWED_TRANSITIONS[WorkItemStatus.OPEN]


def test_workflow_requires_approval_before_resolution() -> None:
    assert (
        WorkItemStatus.RESOLVED in ALLOWED_TRANSITIONS[WorkItemStatus.AWAITING_APPROVAL]
    )
    assert (
        WorkItemStatus.CLOSED
        not in ALLOWED_TRANSITIONS[WorkItemStatus.AWAITING_APPROVAL]
    )


def test_assignment_events_are_distinct() -> None:
    assert ActivityEventType.ASSIGNED.value == "assigned"
    assert ActivityEventType.UNASSIGNED.value == "unassigned"
