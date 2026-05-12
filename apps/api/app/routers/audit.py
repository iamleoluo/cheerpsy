from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    table_name: str | None = Query(None),
    record_id: int | None = Query(None),
    limit: int = Query(default=100, le=500),
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if table_name:
        q = q.filter(AuditLog.table_name == table_name)
    if record_id:
        q = q.filter(AuditLog.record_id == record_id)

    logs = q.order_by(desc(AuditLog.changed_at)).limit(limit).all()

    user_ids = list({l.changed_by for l in logs if l.changed_by})
    names = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        names = {u.id: u.name for u in users}

    return [
        {
            "id": l.id,
            "table_name": l.table_name,
            "record_id": l.record_id,
            "operation": l.operation,
            "changed_by": l.changed_by,
            "changed_by_name": names.get(l.changed_by),
            "changed_at": l.changed_at.isoformat() if l.changed_at else None,
            "before_data": l.before_data,
            "after_data": l.after_data,
            "reason": l.reason,
        }
        for l in logs
    ]
