"""Shared audit logging utility."""

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit(
    db: Session,
    table: str,
    record_id: int,
    operation: str,
    user_id: int,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
):
    """Write an audit log entry. Call before db.commit()."""
    db.add(AuditLog(
        table_name=table,
        record_id=record_id,
        operation=operation,
        changed_by=user_id,
        before_data=before,
        after_data=after,
        reason=reason,
    ))
