from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.auth.password import verify_password
from app.database import get_db
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.gcal_hooks import enqueue_appointments
from app.models.couple_member import CoupleMember
from app.models.user import User
from app.schemas.case import (
    CaseCloseRequest,
    CaseCreate,
    CaseReopenRequest,
    CaseResponse,
    CaseUpdate,
    CoupleCreate,
    CoupleMemberInfo,
)
from app.services import quota_flow
from app.services.audit import write_audit
from app.services.case_numbering import generate_case_number, generate_couple_number
from app.utils.encryption import encrypt_national_id, hmac_national_id

router = APIRouter(prefix="/cases", tags=["cases"])


def _to_response(c: Case, viewer: User | None = None) -> CaseResponse:
    return CaseResponse(
        id=c.id,
        temp_seq=c.temp_seq,
        case_code=c.case_code,
        case_number=c.case_number,
        name=c.name,
        age=c.age,
        birth_date=c.birth_date,
        gender=c.gender,
        phone=c.phone,
        phone_home=c.phone_home,
        address=c.address,
        emergency_contact=c.emergency_contact,
        emergency_phone=c.emergency_phone,
        emergency_phone2=c.emergency_phone2,
        initial_visit_date=c.initial_visit_date,
        funding_source=c.funding_source,
        institution_id=c.institution_id,
        institution_name=c.institution.name if c.institution else None,
        referral_source=c.referral_source,
        session_location=c.session_location,
        therapist_id=c.therapist_id,
        therapist_name=c.therapist.name if c.therapist else None,
        status=c.status,
        billing_cycle=c.billing_cycle,
        has_national_id=c.national_id_encrypted is not None,
        is_designated=c.is_designated,
        case_type=c.case_type,
        members=_couple_members(c, viewer) if c.case_type == "couple" else None,
        notes=c.notes,
        closed_at=c.closed_at,
        closure_reason=c.closure_reason,
    )


def _couple_members(c: Case, viewer: User | None = None) -> list[CoupleMemberInfo]:
    """組出伴侶案的成員清單。心理師只看得到屬於自己的成員個案。"""
    out: list[CoupleMemberInfo] = []
    for link in c.couple_links:
        m = link.member_case
        if m and viewer is not None and viewer.role == "therapist" and m.therapist_id != viewer.id:
            continue
        if m:
            out.append(CoupleMemberInfo(case_id=m.id, name=m.name, role=link.role))
    return out


@router.get("", response_model=list[CaseResponse])
def list_cases(
    status_filter: str | None = Query(None, alias="status"),
    therapist_id: int | None = None,
    billing_cycle: str | None = Query(None, description="once / monthly / multiple"),
    q: str | None = Query(None, description="搜尋個案姓名 / 案號 / 心理師姓名"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Case).options(joinedload(Case.therapist), joinedload(Case.institution))
    if user.role == "therapist":
        query = query.filter(Case.therapist_id == user.id)
    elif therapist_id:
        query = query.filter(Case.therapist_id == therapist_id)
    if status_filter:
        query = query.filter(Case.status == status_filter)
    else:
        # 預設隱藏已結案個案（避免預約名單冗長）；如需查看請顯式帶 status=closed
        query = query.filter(Case.status != "closed")
    if billing_cycle:
        query = query.filter(Case.billing_cycle == billing_cycle)
    if q:
        # 統一搜尋：個案姓名 / 案號（temp + 正式）/ 心理師姓名
        like = f"%{q}%"
        query = query.outerjoin(Case.therapist).filter(
            or_(
                Case.name.ilike(like),
                Case.case_number.ilike(like),
                Case.case_code.ilike(like),
                User.name.ilike(like),
            )
        )
    cases = query.order_by(Case.id.desc()).limit(500).all()
    return [_to_response(c, user) for c in cases]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == "therapist" and c.therapist_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")  # 與不存在相同，不讓人猜 id
    return _to_response(c, user)


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    body: CaseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    next_seq = (db.query(func.coalesce(func.max(Case.temp_seq), 0)).scalar() or 0) + 1

    c = Case(
        temp_seq=next_seq,
        name=body.name,
        age=body.age,
        birth_date=body.birth_date,
        gender=body.gender,
        phone=body.phone,
        emergency_contact=body.emergency_contact,
        initial_visit_date=body.initial_visit_date,
        funding_source=body.funding_source,
        institution_id=body.institution_id if body.funding_source == "institution" else None,
        therapist_id=body.therapist_id if user.role != "therapist" else user.id,
        billing_cycle=body.billing_cycle,
        is_designated=body.is_designated,
        notes=body.notes,
        created_by=user.id,
    )
    if body.national_id:
        c.national_id_encrypted = encrypt_national_id(body.national_id)
        c.national_id_hmac = hmac_national_id(body.national_id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.post("/couple", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_couple_case(
    body: CoupleCreate,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """建立伴侶案：把兩個既有個案綁成一筆合療收費單位（case_type='couple'）。"""
    if len(body.member_case_ids) != 2 or len(set(body.member_case_ids)) != 2:
        raise HTTPException(status_code=400, detail="伴侶案需指定兩個不同的個案")

    members = db.query(Case).filter(Case.id.in_(body.member_case_ids)).all()
    if len(members) != 2:
        raise HTTPException(status_code=400, detail="找不到指定的個案")
    for m in members:
        if m.case_type == "couple":
            raise HTTPException(status_code=400, detail=f"{m.name} 本身是伴侶案，不能再被綁定")

    # 不可重複綁定：任一成員已屬於其他伴侶案
    existing = (
        db.query(CoupleMember)
        .filter(CoupleMember.member_case_id.in_(body.member_case_ids))
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="該個案已屬於其他伴侶案")

    # display_name 留空 → 自動組合
    ordered = {m.id: m for m in members}
    a, b = ordered[body.member_case_ids[0]], ordered[body.member_case_ids[1]]
    display_name = body.display_name or f"{a.name}＆{b.name}（伴侶）"

    couple = Case(
        name=display_name,
        case_type="couple",
        status="ongoing",
        funding_source=body.funding_source,
        institution_id=body.institution_id if body.funding_source == "institution" else None,
        therapist_id=body.therapist_id,
        billing_cycle=body.billing_cycle,
        case_number=generate_couple_number(db),
        created_by=user.id,
    )
    db.add(couple)
    db.flush()  # 取得 couple.id

    for mid in body.member_case_ids:
        db.add(CoupleMember(couple_case_id=couple.id, member_case_id=mid))

    write_audit(db, "cases", couple.id, "CREATE", user.id, None,
                {"case_type": "couple", "members": body.member_case_ids})
    db.commit()
    db.refresh(couple)
    return _to_response(couple)


@router.put("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: int,
    body: CaseUpdate,
    user: User = Depends(RequireRole(["admin", "staff", "therapist"])),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c or (user.role == "therapist" and c.therapist_id != user.id):
        raise HTTPException(status_code=404, detail="Case not found")

    update_data = body.model_dump(exclude_unset=True)
    if user.role == "therapist":
        # 心理師能改自己個案的資料，但不能把個案改派給別人，也不能自行改個案狀態（轉正式／結案走行政流程）
        if update_data.get("therapist_id") not in (None, user.id) or "status" in update_data:
            raise HTTPException(status_code=403, detail="不能改派個案或變更個案狀態，請洽行政人員")
        update_data.pop("therapist_id", None)

    if "national_id" in update_data:
        nid = update_data.pop("national_id")
        if nid:
            c.national_id_encrypted = encrypt_national_id(nid)
            c.national_id_hmac = hmac_national_id(nid)

    if c.case_number and "case_number" in update_data:
        raise HTTPException(status_code=400, detail="Case number cannot be changed once assigned")

    before = {k: getattr(c, k, None) for k in update_data.keys()}
    for key, val in update_data.items():
        setattr(c, key, val)
    if c.funding_source == "self_pay":
        c.institution_id = None
    after = {k: getattr(c, k, None) for k in update_data.keys()}
    write_audit(db, "cases", c.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.post("/{case_id}/activate", response_model=CaseResponse)
def activate_case(
    case_id: int,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    if c.case_number:
        raise HTTPException(status_code=400, detail="Case already has a formal number")
    if c.status != "initial":
        raise HTTPException(status_code=400, detail="Only initial-status cases can be activated")

    missing = []
    if not c.national_id_encrypted:
        missing.append("身份證字號")
    if not c.birth_date:
        missing.append("出生日期")
    if not c.phone:
        missing.append("連絡電話")
    if missing:
        raise HTTPException(status_code=400, detail=f"轉正式前需填寫：{'、'.join(missing)}")

    c.case_number = generate_case_number(db, c)
    c.status = "ongoing"
    write_audit(db, "cases", c.id, "UPDATE", user.id,
                {"status": "initial", "case_number": None},
                {"status": "ongoing", "case_number": c.case_number})
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.post("/{case_id}/close", response_model=CaseResponse)
def close_case(
    case_id: int,
    body: CaseCloseRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """結案個案。

    流程：
      1. 驗證呼叫者密碼（防誤觸）
      2. case.status = "closed"，寫入 closed_at/by 與 closure_reason
      3. 取消所有未來預約（booked 且 lower(time_range) > now）
      4. 機構額度歸零：已預留＋已預約全數釋出，只保留已使用的歷史
      5. write_audit
    """
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="密碼錯誤")

    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="個案不存在")
    if c.status == "closed":
        raise HTTPException(status_code=400, detail="此個案已結案")

    now = datetime.now(timezone.utc)
    prev_status = c.status

    # 4-1) 取消未來 booked 預約
    to_cancel = (
        db.query(Appointment)
        .filter(
            Appointment.case_id == case_id,
            Appointment.status == "booked",
            text("lower(time_range) > now()"),
        )
    )
    cancel_ids = [i for (i,) in to_cancel.with_entities(Appointment.id).all()]
    cancelled = to_cancel.update({Appointment.status: "cancelled"}, synchronize_session=False)
    # 批次 UPDATE 不經過 ORM 事件，Google 日曆同步要明確入列（同一交易）
    enqueue_appointments(db.connection(), cancel_ids)

    # 4-2) 額度歸零（只保留已使用的歷史）
    quotas_zeroed = 0
    for q in db.query(CaseInstitutionQuota).filter(CaseInstitutionQuota.case_id == case_id).all():
        if q.total_count > q.used_count:
            quota_flow.release_on_close(q)
            quotas_zeroed += 1

    c.status = "closed"
    c.closed_at = now
    c.closed_by = user.id
    c.closure_reason = (body.reason or "").strip() or None

    write_audit(
        db, "cases", c.id, "CLOSE", user.id,
        {"status": prev_status},
        {
            "status": "closed",
            "closure_reason": c.closure_reason,
            "cancelled_appointments": cancelled,
            "quotas_zeroed": quotas_zeroed,
        },
    )
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.post("/{case_id}/reopen", response_model=CaseResponse)
def reopen_case(
    case_id: int,
    body: CaseReopenRequest,
    user: User = Depends(RequireRole(["admin", "staff"])),
    db: Session = Depends(get_db),
):
    """復案：把結案個案恢復為 ongoing。

    已歸零的 quota 與已取消的預約不會自動還原（避免狀態混亂）。
    """
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="密碼錯誤")

    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="個案不存在")
    if c.status != "closed":
        raise HTTPException(status_code=400, detail="此個案目前並非結案狀態")

    now = datetime.now(timezone.utc)
    c.status = "ongoing"
    c.reopened_at = now
    c.reopened_by = user.id

    write_audit(
        db, "cases", c.id, "REOPEN", user.id,
        {"status": "closed"},
        {"status": "ongoing", "reopened_at": now.isoformat()},
    )
    db.commit()
    db.refresh(c)
    return _to_response(c)
