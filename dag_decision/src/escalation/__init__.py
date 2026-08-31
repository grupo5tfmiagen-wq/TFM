"""Human Escalation Layer (Modulo 5): cola de revision humana para casos escalados."""
from .service import (
    STATUS_PENDING,
    STATUS_RESOLVED,
    create_escalation,
    get_escalation,
    get_pending_escalation,
    list_pending_escalations,
    resolve_escalation,
)

__all__ = [
    "STATUS_PENDING",
    "STATUS_RESOLVED",
    "create_escalation",
    "get_escalation",
    "get_pending_escalation",
    "list_pending_escalations",
    "resolve_escalation",
]
