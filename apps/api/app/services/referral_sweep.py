"""媒合派案的逾期處理（原本寫在 routers/referrals.py）。

  逾 1 天標記 reminded_at（供待辦顯示）
  逾 3 天 target 轉 expired；整批都 expired 則 dispatch 轉 expired、媒合狀態退回 failed 供行政重新派案

兩個入口共用同一支 sweep_expired：
  * 列表／待辦頁讀取時順便呼叫（routers/referrals.py）
  * gcal_worker 每小時呼叫一次（run_sweep，自己開 session、自己 commit）

冪等：只處理 status='pending' 的 target，且 reminded_at 已有值就不再標記；已 expired 的不會再被撈到。
重複執行不會重複提醒、也不會重複退回。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.referral import ReferralDispatch, ReferralDispatchTarget

logger = logging.getLogger("cheerpsy.referral_sweep")

# 逾 1 個自然日提醒、逾 3 個自然日自動退回（原型 match 定案④）
REMIND_AFTER_DAYS = 1
EXPIRE_AFTER_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def settle_dispatch(db: Session, dispatch: ReferralDispatch) -> None:
    """依 target 狀態收斂 dispatch 與 referral 的狀態。"""
    statuses = [t.status for t in dispatch.targets]
    if not statuses:
        return
    referral = dispatch.referral

    if "accepted" in statuses:
        dispatch.status = "accepted"
        dispatch.resolved_at = dispatch.resolved_at or _now()
        # 先回先得：其餘未回覆者轉「被他人承接」
        for t in dispatch.targets:
            if t.status == "pending":
                t.status = "taken"
                t.responded_at = _now()
        if referral.status in ("new", "matching", "failed"):
            referral.status = "converted"
        return

    if all(s in ("declined", "taken", "expired", "released") for s in statuses):
        dispatch.status = "expired" if "expired" in statuses else "failed"
        dispatch.resolved_at = dispatch.resolved_at or _now()
        if referral.status == "matching":
            referral.status = "failed"


def sweep_expired(db: Session, now: datetime | None = None) -> int:
    now = now or _now()
    remind_before = now - timedelta(days=REMIND_AFTER_DAYS)
    expire_before = now - timedelta(days=EXPIRE_AFTER_DAYS)
    changed = 0

    pending = (
        db.query(ReferralDispatchTarget)
        .join(ReferralDispatch)
        .filter(ReferralDispatchTarget.status == "pending")
        .all()
    )
    for t in pending:
        sent = t.dispatch.dispatched_at
        if sent is None:
            continue
        if sent <= expire_before:
            t.status = "expired"
            t.responded_at = now
            changed += 1
        elif sent <= remind_before and t.reminded_at is None:
            t.reminded_at = now
            changed += 1

    if changed:
        db.flush()
        for dsp in {t.dispatch for t in pending}:
            settle_dispatch(db, dsp)
        db.commit()
    return changed


def run_sweep(session_factory=SessionLocal, now: datetime | None = None) -> int:
    """給背景程序用：自己開 session、自己 commit；出錯只記 log，不丟例外。回傳處理筆數。"""
    db = None
    try:
        db = session_factory()
        n = sweep_expired(db, now=now)
        if n:
            logger.info("referral sweep: %s target(s) updated", n)
        return n
    except Exception:  # noqa: BLE001 — 背景程序不可因單次異常結束
        logger.exception("referral sweep failed")
        try:
            if db is not None:
                db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0
    finally:
        try:
            if db is not None:
                db.close()
        except Exception:  # noqa: BLE001
            pass
