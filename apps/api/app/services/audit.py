"""Shared audit logging utility."""

from datetime import date, datetime
from decimal import Decimal
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
    if isinstance(obj, Decimal):
        # P0 修正：docstring 一直宣稱有處理 Decimal，但原本沒有 isinstance 分支——
        # 帶 Decimal 欄位（金額）的 before/after 存進 JSONB 時會直接丟例外。
        return str(obj)
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
    actor_name: str | None = None,
):
    """Write an audit log entry. Call before db.commit().

    actor_name：共用帳號（如實習心理師）登入時自填的姓名快照，供稽核顯示「實習心理師（王小明）」。
    一般帳號可省略，畫面顯示時回退讀 changed_by 對應的 user.name。見 02 §8 共用帳號設計。
    """
    db.add(AuditLog(
        table_name=table,
        record_id=record_id,
        operation=operation,
        changed_by=user_id,
        actor_name=actor_name,
        before_data=_jsonify(before),
        after_data=_jsonify(after),
        reason=reason,
    ))
