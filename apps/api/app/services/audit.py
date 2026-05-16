"""Shared audit logging utility."""

from datetime import date, datetime
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def _jsonify(obj):
    """Recursively convert non-JSON-serializable types (date, datetime, Decimal) to strings."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


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
        before_data=_jsonify(before),
        after_data=_jsonify(after),
        reason=reason,
    ))
