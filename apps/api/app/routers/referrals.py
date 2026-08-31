from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.referral import (
    CANCEL_REASONS,
    DECLINE_REASONS,
    ReferralDesignation,
    ReferralDispatch,
    ReferralDispatchTarget,
    ReferralRequest,
    ReferralSlotOffer,
)
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/referrals", tags=["referrals"])

STAFF = ["admin", "accountant", "staff"]
ADMIN_STAFF = ["admin", "staff"]

# 逾 1 個自然日提醒、逾 3 個自然日自動退回（原型 match 定案④）
REMIND_AFTER_DAYS = 1
EXPIRE_AFTER_DAYS = 3
MAX_DISPATCH_TARGETS = 3


# ---------------------------------------------------------------------------
# 派案碼：YYMMDD + 流水號3碼，建立需求表時產生
# ---------------------------------------------------------------------------
def _next_dispatch_code(db: Session, today: date | None = None) -> str:
    d = today or date.today()
    prefix = d.strftime("%y%m%d")
    n = (
        db.query(func.count(ReferralRequest.id))
        .filter(ReferralRequest.dispatch_code.like(f"{prefix}%"))
        .scalar()
        or 0
    )
    return f"{prefix}{n + 1:03d}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 逾期處理：讀取時延遲結算，不需要排程器
#   逾 1 天標記 reminded_at（供待辦顯示）
#   逾 3 天 target 轉 expired；整批都 expired 則 dispatch 轉 expired、
#   媒合狀態退回 failed 供行政重新派案
# ---------------------------------------------------------------------------
def sweep_expired(db: Session) -> int:
    now = _now()
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
            _settle_dispatch(db, dsp)
        db.commit()
    return changed


def _settle_dispatch(db: Session, dispatch: ReferralDispatch) -> None:
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


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ReferralIn(BaseModel):
    name: str
    age: int | None = None
    gender: str | None = None
    phone: str | None = None
    referral_source: str | None = None
    chief_complaint: str | None = None
    complaint_note: str | None = None
    consultation_mode: str = "individual"
    partner_name: str | None = None
    funding_source: str = "self_pay"
    plan_id: int | None = None
    designated_therapist_ids: list[int] = []

    @model_validator(mode="after")
    def _check(self):
        if self.funding_source not in ("self_pay", "institution"):
            raise ValueError("funding_source 只能是 self_pay 或 institution")
        if self.funding_source == "institution" and self.plan_id is None:
            raise ValueError("機構案需指定方案")
        if len(self.designated_therapist_ids) > MAX_DISPATCH_TARGETS:
            raise ValueError(f"指定心理師上限 {MAX_DISPATCH_TARGETS} 位")
        if len(set(self.designated_therapist_ids)) != len(self.designated_therapist_ids):
            raise ValueError("指定心理師不可重複")
        if self.consultation_mode in ("couple", "visitation") and not self.partner_name:
            raise ValueError("伴侶諮商／會面交往需填第二位個案姓名")
        return self


class SlotIn(BaseModel):
    slot_date: date
    start_time: str
    end_time: str


class AcceptIn(BaseModel):
    """承接時提供 1–3 個可預約時段，第一個必填。"""

    slots: list[SlotIn]

    @model_validator(mode="after")
    def _check(self):
        if not self.slots:
            raise ValueError("至少需提供 1 個可預約時段")
        if len(self.slots) > 3:
            raise ValueError("最多 3 個時段")
        return self


class DeclineIn(BaseModel):
    reason: str
    note: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.reason not in DECLINE_REASONS:
            raise ValueError(f"reason 需為 {list(DECLINE_REASONS)}")
        if self.reason == "other" and not (self.note or "").strip():
            raise ValueError("選擇「其他」時需填寫原因")
        return self


class DispatchIn(BaseModel):
    therapist_ids: list[int]

    @model_validator(mode="after")
    def _check(self):
        if not self.therapist_ids:
            raise ValueError("至少需選 1 位心理師")
        if len(self.therapist_ids) > MAX_DISPATCH_TARGETS:
            raise ValueError(f"一次最多派給 {MAX_DISPATCH_TARGETS} 位（先回先得）")
        if len(set(self.therapist_ids)) != len(self.therapist_ids):
            raise ValueError("心理師不可重複")
        return self


class CancelIn(BaseModel):
    reason: str
    note: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.reason not in CANCEL_REASONS:
            raise ValueError(f"reason 需為 {list(CANCEL_REASONS)}")
        return self


class SlotOut(BaseModel):
    id: int
    seq: int
    slot_date: date
    start_time: str
    end_time: str
    is_selected: bool


class TargetOut(BaseModel):
    id: int
    therapist_id: int
    therapist_name: str | None
    status: str
    decline_reason: str | None
    decline_note: str | None
    responded_at: datetime | None
    slots: list[SlotOut]


class DispatchOut(BaseModel):
    id: int
    seq: int
    status: str
    dispatched_at: datetime
    resolved_at: datetime | None
    targets: list[TargetOut]


class ReferralOut(BaseModel):
    id: int
    dispatch_code: str
    name: str
    age: int | None
    gender: str | None
    phone: str | None
    referral_source: str | None
    chief_complaint: str | None
    complaint_note: str | None
    consultation_mode: str
    partner_name: str | None
    funding_source: str
    plan_id: int | None
    plan_name: str | None
    status: str
    cancel_reason: str | None
    designated_therapists: list[str]
    dispatch_count: int
    case_id: int | None
    case_number: str | None
    created_at: datetime
    # 親友介紹需提示雙重關係（原型 pool 倫理提示）
    dual_relationship_warning: bool


def _slot_out(s: ReferralSlotOffer) -> SlotOut:
    return SlotOut(
        id=s.id, seq=s.seq, slot_date=s.slot_date,
        start_time=s.start_time, end_time=s.end_time,
        is_selected=bool(s.is_selected),
    )


def _target_out(t: ReferralDispatchTarget) -> TargetOut:
    return TargetOut(
        id=t.id, therapist_id=t.therapist_id,
        therapist_name=t.therapist.name if t.therapist else None,
        status=t.status, decline_reason=t.decline_reason, decline_note=t.decline_note,
        responded_at=t.responded_at, slots=[_slot_out(s) for s in t.slots],
    )


def _referral_out(r: ReferralRequest) -> ReferralOut:
    src = (r.referral_source or "")
    return ReferralOut(
        id=r.id, dispatch_code=r.dispatch_code, name=r.name, age=r.age, gender=r.gender,
        phone=r.phone, referral_source=r.referral_source,
        chief_complaint=r.chief_complaint, complaint_note=r.complaint_note,
        consultation_mode=r.consultation_mode, partner_name=r.partner_name,
        funding_source=r.funding_source, plan_id=r.plan_id,
        plan_name=r.plan.name if r.plan else None,
        status=r.status, cancel_reason=r.cancel_reason,
        designated_therapists=[d.therapist.name for d in r.designations if d.therapist],
        dispatch_count=len(r.dispatches),
        case_id=r.case_id, case_number=r.case.case_number if r.case else None,
        created_at=r.created_at,
        dual_relationship_warning=("親友" in src or "介紹" in src),
    )


# ---------------------------------------------------------------------------
# 行政端
# ---------------------------------------------------------------------------
@router.get("", response_model=list[ReferralOut])
def list_referrals(
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = Query(None, description="姓名／電話／機構方案即時搜尋"),
    closed: bool = Query(False, description="true 則回傳媒合結案表"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sweep_expired(db)
    query = db.query(ReferralRequest)
    closed_states = ["cancelled", "closed", "intake_done"]
    if closed:
        query = query.filter(ReferralRequest.status.in_(closed_states))
    else:
        # 初診有到後案件離開本列表、轉入個案管理（原型 match 定案⑥）
        query = query.filter(~ReferralRequest.status.in_(closed_states))
    if status_filter:
        query = query.filter(ReferralRequest.status == status_filter)
    rows = query.order_by(ReferralRequest.id.desc()).all()

    if q:
        needle = q.strip().lower()
        rows = [
            r for r in rows
            if needle in (r.name or "").lower()
            or needle in (r.phone or "").lower()
            or needle in ((r.plan.name if r.plan else "") or "").lower()
        ]
    return [_referral_out(r) for r in rows]


@router.get("/{referral_id}/dispatches", response_model=list[DispatchOut])
def list_dispatches(
    referral_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """媒合子列表：歷次派案批次。一列一批次。"""
    sweep_expired(db)
    r = db.query(ReferralRequest).filter(ReferralRequest.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return [
        DispatchOut(
            id=d.id, seq=d.seq, status=d.status,
            dispatched_at=d.dispatched_at, resolved_at=d.resolved_at,
            targets=[_target_out(t) for t in d.targets],
        )
        for d in r.dispatches
    ]


@router.post("", response_model=ReferralOut, status_code=http.HTTP_201_CREATED)
def create_referral(
    body: ReferralIn,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    r = ReferralRequest(
        dispatch_code=_next_dispatch_code(db),
        name=body.name.strip(),
        age=body.age, gender=body.gender, phone=body.phone,
        referral_source=body.referral_source,
        chief_complaint=body.chief_complaint, complaint_note=body.complaint_note,
        consultation_mode=body.consultation_mode, partner_name=body.partner_name,
        funding_source=body.funding_source, plan_id=body.plan_id,
        created_by=user.id,
    )
    db.add(r)
    db.flush()
    for tid in body.designated_therapist_ids:
        db.add(ReferralDesignation(referral_id=r.id, therapist_id=tid))
    db.commit()
    db.refresh(r)
    write_audit(db, "referral_requests", r.id, "INSERT", user.id, None,
                {"dispatch_code": r.dispatch_code, "name": r.name})
    db.commit()
    return _referral_out(r)


@router.put("/{referral_id}", response_model=ReferralOut)
def update_referral(
    referral_id: int,
    body: ReferralIn,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    r = db.query(ReferralRequest).filter(ReferralRequest.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    # 初診有到後個資改到個案管理的「個人資料」分頁（原型 cases 定案③）
    if r.status == "intake_done":
        raise HTTPException(
            status_code=400,
            detail="初診有到後個資請於個案管理修改，此需求表已鎖定",
        )
    before = {"name": r.name, "phone": r.phone, "chief_complaint": r.chief_complaint}
    r.name = body.name.strip()
    r.age, r.gender, r.phone = body.age, body.gender, body.phone
    r.referral_source = body.referral_source
    r.chief_complaint, r.complaint_note = body.chief_complaint, body.complaint_note
    r.consultation_mode, r.partner_name = body.consultation_mode, body.partner_name
    r.funding_source, r.plan_id = body.funding_source, body.plan_id

    db.query(ReferralDesignation).filter(ReferralDesignation.referral_id == r.id).delete()
    db.flush()
    for tid in body.designated_therapist_ids:
        db.add(ReferralDesignation(referral_id=r.id, therapist_id=tid))

    write_audit(db, "referral_requests", r.id, "UPDATE", user.id, before,
                {"name": r.name, "phone": r.phone, "chief_complaint": r.chief_complaint})
    db.commit()
    db.refresh(r)
    return _referral_out(r)


@router.post("/{referral_id}/dispatch", response_model=DispatchOut, status_code=http.HTTP_201_CREATED)
def dispatch(
    referral_id: int,
    body: DispatchIn,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    """派案：同時發送 1–3 位、先回先得。"""
    r = db.query(ReferralRequest).filter(ReferralRequest.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r.status in ("cancelled", "closed", "intake_done"):
        raise HTTPException(status_code=400, detail=f"狀態 {r.status} 不可再派案")
    if any(d.status == "open" for d in r.dispatches):
        raise HTTPException(status_code=400, detail="尚有進行中的派案批次，請先等待回覆或取消")

    therapists = db.query(User).filter(User.id.in_(body.therapist_ids)).all()
    if len(therapists) != len(body.therapist_ids):
        raise HTTPException(status_code=404, detail="部分心理師不存在")
    bad = [t.name for t in therapists if t.role != "therapist"]
    if bad:
        raise HTTPException(status_code=400, detail=f"非心理師帳號不可派案：{', '.join(bad)}")

    d = ReferralDispatch(referral_id=r.id, seq=len(r.dispatches) + 1)
    db.add(d)
    db.flush()
    for tid in body.therapist_ids:
        db.add(ReferralDispatchTarget(dispatch_id=d.id, therapist_id=tid))
    r.status = "matching"
    db.commit()
    db.refresh(d)
    write_audit(db, "referral_dispatches", d.id, "INSERT", user.id, None,
                {"referral_id": r.id, "seq": d.seq, "therapist_ids": body.therapist_ids})
    db.commit()
    return DispatchOut(
        id=d.id, seq=d.seq, status=d.status, dispatched_at=d.dispatched_at,
        resolved_at=d.resolved_at, targets=[_target_out(t) for t in d.targets],
    )


@router.post("/{referral_id}/cancel", response_model=ReferralOut)
def cancel_referral(
    referral_id: int,
    body: CancelIn,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    r = db.query(ReferralRequest).filter(ReferralRequest.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r.status in ("closed", "intake_done"):
        raise HTTPException(status_code=400, detail="已結案的個案不可取消媒合")
    before = {"status": r.status}
    r.status = "cancelled"
    r.cancel_reason, r.cancel_note = body.reason, body.note
    r.closed_at = _now()
    for d in r.dispatches:
        if d.status == "open":
            d.status = "cancelled"
            d.resolved_at = _now()
    write_audit(db, "referral_requests", r.id, "UPDATE", user.id, before,
                {"status": "cancelled", "reason": body.reason})
    db.commit()
    db.refresh(r)
    return _referral_out(r)


class IntakeIn(BaseModel):
    national_id: str
    birth_date: date | None = None
    address: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    therapist_id: int


@router.post("/{referral_id}/intake-arrived", response_model=ReferralOut)
def intake_arrived(
    referral_id: int,
    body: IntakeIn,
    user: User = Depends(RequireRole(ADMIN_STAFF)),
    db: Session = Depends(get_db),
):
    """初診有到 → 建立個案並產生病歷號，案件離開媒合列表。"""
    from app.services.case_numbering import generate_case_number
    from app.utils.encryption import encrypt_national_id, hmac_national_id

    r = db.query(ReferralRequest).filter(ReferralRequest.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if r.status == "intake_done":
        raise HTTPException(status_code=400, detail="此案已完成初診")
    if r.status not in ("converted", "matching"):
        raise HTTPException(status_code=400, detail=f"狀態 {r.status} 不可登錄初診")

    c = Case(
        name=r.name, age=r.age, gender=r.gender, phone=r.phone,
        national_id_encrypted=encrypt_national_id(body.national_id),
        national_id_hmac=hmac_national_id(body.national_id),
        birth_date=body.birth_date, address=body.address,
        emergency_contact=body.emergency_contact, emergency_phone=body.emergency_phone,
        initial_visit_date=date.today(),
        funding_source=r.funding_source,
        referral_source=r.referral_source,
        therapist_id=body.therapist_id,
        status="ongoing",
        consultation_mode=r.consultation_mode,
        referral_id=r.id,
        dispatch_code=r.dispatch_code,
        chief_complaint=r.chief_complaint,
        complaint_note=r.complaint_note,
        is_designated=bool(r.designations),
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    c.case_number = generate_case_number(db, c)

    r.status = "intake_done"
    r.intake_at = _now()
    r.case_id = c.id
    r.closed_at = _now()
    db.commit()
    db.refresh(r)
    write_audit(db, "referral_requests", r.id, "UPDATE", user.id,
                {"status": "converted"},
                {"status": "intake_done", "case_id": c.id, "case_number": c.case_number})
    db.commit()
    return _referral_out(r)


class NoShowIn(BaseModel):
    reason: str


@router.post("/{referral_id}/intake-no-show", response_model=ReferralOut)
def intake_no_show(
    referral_id: int,
    body: NoShowIn,
    user: User = Depends(RequireRole(ADMIN_STAFF)),
    db: Session = Depends(get_db),
):
    r = db.query(ReferralRequest).filter(ReferralRequest.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    r.no_show_reason = body.reason
    write_audit(db, "referral_requests", r.id, "UPDATE", user.id, None,
                {"intake_no_show": body.reason})
    db.commit()
    db.refresh(r)
    return _referral_out(r)


# ---------------------------------------------------------------------------
# 心理師端：派案邀請
# ---------------------------------------------------------------------------
class InviteOut(BaseModel):
    target_id: int
    referral_id: int
    dispatch_code: str
    name: str
    age: int | None
    gender: str | None
    chief_complaint: str | None
    complaint_note: str | None
    consultation_mode: str
    funding_source: str
    plan_name: str | None
    status: str
    dispatched_at: datetime
    # 指定心理師僅三種顯示（原型 pool 定案②）
    designation: str  # "self" 指定本人／"none" 不指定／"other_unavailable"
    # 卡片顯示「另有 N 位心理師評估中」（定案①）
    others_evaluating: int
    is_overdue: bool
    dual_relationship_warning: bool
    slots: list[SlotOut]
    decline_reason: str | None


def _invite_out(t: ReferralDispatchTarget, me: int) -> InviteOut:
    d = t.dispatch
    r = d.referral
    designated_ids = {x.therapist_id for x in r.designations}
    if me in designated_ids:
        designation = "self"
    elif designated_ids:
        designation = "other_unavailable"
    else:
        designation = "none"
    src = r.referral_source or ""
    return InviteOut(
        target_id=t.id, referral_id=r.id, dispatch_code=r.dispatch_code,
        name=r.name, age=r.age, gender=r.gender,
        chief_complaint=r.chief_complaint, complaint_note=r.complaint_note,
        consultation_mode=r.consultation_mode, funding_source=r.funding_source,
        plan_name=r.plan.name if r.plan else None,
        status=t.status, dispatched_at=d.dispatched_at,
        designation=designation,
        others_evaluating=sum(1 for x in d.targets if x.id != t.id and x.status == "pending"),
        is_overdue=(t.status == "pending" and t.reminded_at is not None),
        dual_relationship_warning=("親友" in src or "介紹" in src),
        slots=[_slot_out(s) for s in t.slots],
        decline_reason=t.decline_reason,
    )


@router.get("/invites", response_model=list[InviteOut])
def my_invites(
    tab: str = Query("pending", pattern="^(pending|accepted|closed)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """心理師端三分頁：待回覆／已承接／已結束。"""
    sweep_expired(db)
    q = db.query(ReferralDispatchTarget).filter(
        ReferralDispatchTarget.therapist_id == user.id
    )
    if tab == "pending":
        q = q.filter(ReferralDispatchTarget.status == "pending")
    elif tab == "accepted":
        q = q.filter(ReferralDispatchTarget.status == "accepted")
    else:
        # 已結束＝已婉拒／已退回／被他人承接／承接後釋出（原型 pool 定案④）
        q = q.filter(ReferralDispatchTarget.status.in_(["declined", "expired", "taken", "released"]))
    return [_invite_out(t, user.id) for t in q.order_by(ReferralDispatchTarget.id.desc()).all()]


def _my_pending_target(db: Session, target_id: int, user: User) -> ReferralDispatchTarget:
    t = db.query(ReferralDispatchTarget).filter(ReferralDispatchTarget.id == target_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if t.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="不是你的派案邀請")
    if t.status != "pending":
        raise HTTPException(status_code=400, detail=f"此邀請已為 {t.status}，不可再回覆")
    return t


@router.post("/invites/{target_id}/accept", response_model=InviteOut)
def accept_invite(
    target_id: int,
    body: AcceptIn,
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    t = _my_pending_target(db, target_id, user)
    # 先回先得：同批次已有人承接就擋下
    if any(x.status == "accepted" for x in t.dispatch.targets):
        t.status = "taken"
        t.responded_at = _now()
        db.commit()
        raise HTTPException(status_code=409, detail="此案已被其他心理師承接")

    t.status = "accepted"
    t.responded_at = _now()
    for i, s in enumerate(body.slots, start=1):
        db.add(ReferralSlotOffer(
            target_id=t.id, seq=i, slot_date=s.slot_date,
            start_time=s.start_time, end_time=s.end_time,
        ))
    db.flush()
    _settle_dispatch(db, t.dispatch)
    db.commit()
    db.refresh(t)
    return _invite_out(t, user.id)


@router.post("/invites/{target_id}/decline", response_model=InviteOut)
def decline_invite(
    target_id: int,
    body: DeclineIn,
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    t = _my_pending_target(db, target_id, user)
    t.status = "declined"
    t.decline_reason, t.decline_note = body.reason, body.note
    t.responded_at = _now()
    db.flush()
    _settle_dispatch(db, t.dispatch)
    db.commit()
    db.refresh(t)
    return _invite_out(t, user.id)
