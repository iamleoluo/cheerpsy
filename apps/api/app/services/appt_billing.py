"""預約上的「金流資訊」：付款方式、機構額度。

只負責額度的挑選與流轉，不碰流水帳冊、核銷、對帳、月結（那些已移除）。
額度三態的搬動交給 quota_flow（不修改它）；這裡包一層「不擋預約」的處理：
額度不足、已過期、沒有額度時，預約照常建立，只回傳 warnings 讓前端提示。
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.case_institution_quota import CaseInstitutionQuota
from app.services import quota_flow


def _locked(db: Session, quota_id: int) -> CaseInstitutionQuota | None:
    return (
        db.query(CaseInstitutionQuota)
        .filter(CaseInstitutionQuota.id == quota_id)
        .with_for_update(of=CaseInstitutionQuota)
        .first()
    )


def _in_validity(q: CaseInstitutionQuota, on: date) -> bool:
    return (q.valid_from is None or q.valid_from <= on) and (q.valid_until is None or q.valid_until >= on)


def resolve_quota(
    db: Session,
    case_id: int,
    funding_source: str,
    quota_id: int | None,
    appt_date: date,
) -> tuple[CaseInstitutionQuota | None, list[str]]:
    """挑出這場預約要佔用的額度。回傳 (額度或 None, warnings)。

    永遠不因額度問題拒絕預約：沒有可用額度時回 (None, ["…提示…"])，預約照建、不佔額度。
    只有「資料本身不合理」（付款方式不認得、指定的額度不存在或不屬於此個案）才回 4xx。
    """
    warnings: list[str] = []
    if funding_source == "self_pay":
        return None, warnings
    if funding_source != "institution":
        raise HTTPException(status_code=400, detail=f"未支援的付款方式：{funding_source}")

    if quota_id is not None:
        q = _locked(db, quota_id)
        if q is None:
            raise HTTPException(status_code=404, detail="額度不存在")
        if q.case_id != case_id:
            raise HTTPException(status_code=400, detail="額度不屬於此個案")
        if not _in_validity(q, appt_date):
            warnings.append(f"預約日 {appt_date} 不在額度有效期間內")
        if q.reserved_count < 1:
            warnings.append(
                f"機構額度不足（總 {q.total_count} 堂、已用 {q.used_count}、剩餘 {q.reserved_count}），此場預約不佔額度"
            )
            return None, warnings
        return q, warnings

    # 自動挑：有效期內、還有剩餘者，依到期日先到先用
    rows = (
        db.query(CaseInstitutionQuota)
        .filter(
            CaseInstitutionQuota.case_id == case_id,
            or_(CaseInstitutionQuota.valid_from.is_(None), CaseInstitutionQuota.valid_from <= appt_date),
            or_(CaseInstitutionQuota.valid_until.is_(None), CaseInstitutionQuota.valid_until >= appt_date),
            CaseInstitutionQuota.reserved_count > 0,
            CaseInstitutionQuota.status == "active",
        )
        .order_by(CaseInstitutionQuota.valid_until.asc().nullslast(), CaseInstitutionQuota.id.asc())
        .all()
    )
    if rows:
        return _locked(db, rows[0].id), warnings
    has_any = db.query(CaseInstitutionQuota.id).filter(CaseInstitutionQuota.case_id == case_id).first()
    warnings.append(
        f"該個案於 {appt_date} 沒有可用的機構額度（額度已用完或已過期），此場預約不佔額度"
        if has_any else "該個案尚未設定機構額度，此場預約不佔額度"
    )
    return None, warnings


def hold_quota(q: CaseInstitutionQuota | None) -> None:
    """排預約：已預留 → 已預約。resolve_quota 已確認有剩餘，這裡不會丟例外。"""
    if q is not None:
        quota_flow.reserve_to_booked(q)


def _flow_quietly(db: Session, quota_id: int | None, step) -> None:
    """取消／未到／報到時的額度流轉。狀態異常（例如歷史資料）只略過，不擋住報到或取消。"""
    if not quota_id:
        return
    q = _locked(db, quota_id)
    if q is None:
        return
    try:
        step(q)
    except HTTPException:
        pass


def release_quota(db: Session, quota_id: int | None) -> None:
    """取消／未到：已預約 → 退回已預留。"""
    _flow_quietly(db, quota_id, quota_flow.booked_to_reserved)


def consume_quota(db: Session, quota_id: int | None) -> None:
    """報到「已到」：已預約 → 已使用。"""
    _flow_quietly(db, quota_id, quota_flow.booked_to_used)


def quota_summary(db: Session, quota_id: int | None) -> dict | None:
    """日曆與預約列表顯示用：總堂數、已用、剩餘、是否最後一次、機構名稱。"""
    if not quota_id:
        return None
    q = db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.id == quota_id).first()
    if q is None:
        return None
    return {
        "institution_name": q.institution.name if q.institution else None,
        "used": q.used_count,
        "total": q.total_count,
        "remaining": q.reserved_count,
        "is_last": (q.reserved_count + q.booked_count) == 1,
    }
