"""媒合管理的業務邏輯。刻意保持精簡——這只是一個小的子系統，媒合出第一次
（初診）預約後就交棒給既有的個案／預約系統，不重造第二套。

「轉預約」「初診有到」直接重用 app.routers.cases / app.routers.appointments
裡已經寫好的 create_case()／create_appointment()／activate_case()／
check_in()——這些本來就是可以直接當函式呼叫的 plain function（FastAPI 的
Depends 只是預設值，直接傳真的 user/db 進去一樣能跑），這樣衝突檢查、額度
扣減、報價、案號規則全部照舊，不必在這裡重寫一份。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.case import Case
from app.models.user import User
from app.referral.models.batch import ReferralBatch, ReferralBatchMember
from app.referral.models.referral import Referral
from app.referral.rules.numbering import generate_referral_code
from app.routers.appointments import perform_check_in as _check_in
from app.routers.appointments import create_appointment as _create_appointment
from app.routers.cases import activate_case as _activate_case
from app.routers.cases import create_case as _create_case
from app.schemas.appointment import AppointmentCreate, CheckInRequest
from app.schemas.case import CaseCreate
from app.services.audit import write_audit
from app.utils.encryption import encrypt_national_id, hmac_national_id

RETURN_DAYS = 3  # 逾 3 個自然日無人回覆，批次自動退回
DECLINE_REASONS = ["unavailable", "not_specialty", "dual_relationship", "other"]
ACTIVE_STATUSES = ["new", "matching", "unmatched", "accepted", "booked"]


def process_timeouts(db: Session) -> None:
    """Compute-on-read：逾時批次自動轉「不成功／已退回」。跟
    materialize_due_appointments() 一樣，沒有排程器，在讀取列表時順便算。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETURN_DAYS)
    open_batches = (
        db.query(ReferralBatch)
        .filter(ReferralBatch.is_open.is_(True), ReferralBatch.sent_at <= cutoff)
        .all()
    )
    for batch in open_batches:
        for m in batch.members:
            if m.reply_status == "pending":
                m.reply_status = "expired"
                m.replied_at = datetime.now(timezone.utc)
        batch.is_open = False
        referral = batch.referral
        if referral.status == "matching":
            referral.status = "unmatched"
    if open_batches:
        db.commit()


def _issues_json(issues: list[str] | None) -> str | None:
    return json.dumps(issues, ensure_ascii=False) if issues else None


def create_referral(db: Session, user: User, body) -> Referral:
    referral = Referral(
        referral_code=generate_referral_code(db),
        name=body.name,
        age=body.age,
        gender=body.gender,
        phone=body.phone,
        mode=body.mode,
        institution_id=body.institution_id,
        funding_note=body.funding_note,
        issues=_issues_json(body.issues),
        issue_note=body.issue_note,
        designated_therapist_id=body.designated_therapist_id,
        source=body.source,
        availability=body.availability,
        note=body.note,
        created_by=user.id,
    )
    db.add(referral)
    db.flush()
    write_audit(db, "referrals", referral.id, "CREATE", user.id, None, {"referral_code": referral.referral_code})
    db.commit()
    db.refresh(referral)
    return referral


def update_referral(db: Session, user: User, referral: Referral, body) -> Referral:
    if referral.status in ("converted", "cancelled", "closed"):
        raise HTTPException(status_code=400, detail="此媒合案已結束，個資請至個案管理修改")
    update_data = body.model_dump(exclude_unset=True)
    if "issues" in update_data:
        update_data["issues"] = _issues_json(update_data.pop("issues"))
    before = {k: getattr(referral, k, None) for k in update_data.keys()}
    for key, val in update_data.items():
        setattr(referral, key, val)
    write_audit(db, "referrals", referral.id, "UPDATE", user.id, before, update_data)
    db.commit()
    db.refresh(referral)
    return referral


def assign_therapists(db: Session, user: User, referral: Referral, therapist_ids: list[int]) -> ReferralBatch:
    if referral.status not in ("new", "unmatched"):
        raise HTTPException(status_code=400, detail=f"目前狀態（{referral.status}）不可派案")
    if not (1 <= len(therapist_ids) <= 3):
        raise HTTPException(status_code=400, detail="每次派案需指定 1～3 位心理師")
    if len(set(therapist_ids)) != len(therapist_ids):
        raise HTTPException(status_code=400, detail="心理師不可重複")

    prev_seq = db.query(ReferralBatch).filter(ReferralBatch.referral_id == referral.id).count()
    batch = ReferralBatch(referral_id=referral.id, batch_seq=prev_seq + 1, created_by=user.id)
    db.add(batch)
    db.flush()
    for tid in therapist_ids:
        db.add(ReferralBatchMember(batch_id=batch.id, therapist_id=tid))
    referral.status = "matching"
    write_audit(db, "referrals", referral.id, "ASSIGN", user.id, None, {"therapist_ids": therapist_ids, "batch_seq": batch.batch_seq})
    db.commit()
    db.refresh(batch)
    return batch


def _current_open_member(db: Session, referral: Referral, therapist_id: int) -> ReferralBatchMember:
    batch = (
        db.query(ReferralBatch)
        .filter(ReferralBatch.referral_id == referral.id, ReferralBatch.is_open.is_(True))
        .order_by(ReferralBatch.id.desc())
        .first()
    )
    if not batch:
        raise HTTPException(status_code=400, detail="目前沒有進行中的派案批次")
    member = next((m for m in batch.members if m.therapist_id == therapist_id), None)
    if not member:
        raise HTTPException(status_code=404, detail="找不到此派案邀請")
    if member.reply_status != "pending":
        raise HTTPException(status_code=400, detail=f"此邀請已回覆過（{member.reply_status}）")
    return member


def accept_invite(db: Session, therapist: User, member_id: int, slots: list[str]) -> ReferralBatchMember:
    member = db.query(ReferralBatchMember).filter(ReferralBatchMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="找不到此派案邀請")
    if member.therapist_id != therapist.id:
        raise HTTPException(status_code=403, detail="只能回覆自己的派案邀請")
    if member.reply_status != "pending":
        raise HTTPException(status_code=400, detail=f"此邀請已回覆過（{member.reply_status}）")
    if not (1 <= len(slots) <= 3):
        raise HTTPException(status_code=400, detail="請提供 1～3 個可預約時段")

    batch = member.batch
    referral = batch.referral
    member.reply_status = "accepted"
    member.proposed_slots = json.dumps(slots)
    member.replied_at = datetime.now(timezone.utc)
    for sibling in batch.members:
        if sibling.id != member.id and sibling.reply_status == "pending":
            sibling.reply_status = "superseded"
            sibling.replied_at = datetime.now(timezone.utc)
    batch.is_open = False
    referral.status = "accepted"
    referral.accepted_therapist_id = therapist.id
    write_audit(db, "referrals", referral.id, "ACCEPT", therapist.id, None, {"therapist_id": therapist.id, "slots": slots})
    db.commit()
    db.refresh(member)
    return member


def decline_invite(db: Session, therapist: User, member_id: int, reason: str) -> ReferralBatchMember:
    member = db.query(ReferralBatchMember).filter(ReferralBatchMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="找不到此派案邀請")
    if member.therapist_id != therapist.id:
        raise HTTPException(status_code=403, detail="只能回覆自己的派案邀請")
    if member.reply_status != "pending":
        raise HTTPException(status_code=400, detail=f"此邀請已回覆過（{member.reply_status}）")
    if reason not in DECLINE_REASONS:
        raise HTTPException(status_code=400, detail=f"reason 必須是 {DECLINE_REASONS} 之一")

    member.reply_status = "declined"
    member.decline_reason = reason
    member.replied_at = datetime.now(timezone.utc)
    batch = member.batch
    referral = batch.referral
    if all(m.reply_status != "pending" for m in batch.members) and all(m.reply_status != "accepted" for m in batch.members):
        batch.is_open = False
        referral.status = "unmatched"
    write_audit(db, "referrals", referral.id, "DECLINE", therapist.id, None, {"therapist_id": therapist.id, "reason": reason})
    db.commit()
    db.refresh(member)
    return member


def release_invite(db: Session, therapist: User, member_id: int) -> ReferralBatchMember:
    """承接後釋出：心理師已承接但轉預約前決定放棄，行政需重新派案。"""
    member = db.query(ReferralBatchMember).filter(ReferralBatchMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="找不到此派案紀錄")
    if member.therapist_id != therapist.id:
        raise HTTPException(status_code=403, detail="只能操作自己承接的案件")
    if member.reply_status != "accepted":
        raise HTTPException(status_code=400, detail="只有已承接的邀請可以釋出")
    referral = member.batch.referral
    if referral.status != "accepted":
        raise HTTPException(status_code=400, detail=f"目前狀態（{referral.status}）不可釋出")

    member.reply_status = "released"
    member.replied_at = datetime.now(timezone.utc)
    referral.status = "unmatched"
    referral.accepted_therapist_id = None
    write_audit(db, "referrals", referral.id, "RELEASE", therapist.id, None, {"therapist_id": therapist.id})
    db.commit()
    db.refresh(member)
    return member


def cancel_referral(db: Session, user: User, referral: Referral, reason: str) -> Referral:
    if referral.status in ("converted", "cancelled", "closed"):
        raise HTTPException(status_code=400, detail="此媒合案已結束")
    referral.status = "cancelled"
    referral.close_reason = reason
    referral.closed_at = datetime.now(timezone.utc)
    write_audit(db, "referrals", referral.id, "CANCEL", user.id, None, {"reason": reason})
    db.commit()
    db.refresh(referral)
    return referral


def convert_to_appointment(db: Session, user: User, referral: Referral, body) -> Referral:
    """轉預約：直接開啟預約視窗並帶入個案資料，存檔後同步寫入診間日曆
    （cheerpsy_v7_spec_extracted.md「媒合管理」）。

    第一次轉預約會順便建立正式個案（暫時狀態，temp_seq 階段，跟一般新增
    個案一樣）；若是初診未到後選擇「重新安排預約」，個案已經存在，這裡
    只補一筆新的 Appointment，並把心理師換成新承接的人。
    """
    if referral.status != "accepted":
        raise HTTPException(status_code=400, detail=f"目前狀態（{referral.status}）不可轉預約")
    if not referral.accepted_therapist_id:
        raise HTTPException(status_code=400, detail="尚未有心理師承接")

    if referral.converted_case_id:
        case = db.query(Case).filter(Case.id == referral.converted_case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="原個案不存在")
        if case.therapist_id != referral.accepted_therapist_id:
            case.therapist_id = referral.accepted_therapist_id
            db.flush()
    else:
        case_body = CaseCreate(
            name=referral.name,
            age=referral.age,
            gender=referral.gender,
            phone=referral.phone,
            funding_source=body.funding_source,
            institution_id=referral.institution_id if body.funding_source == "institution" else None,
            therapist_id=referral.accepted_therapist_id,
            billing_cycle="once",
            is_designated=(referral.designated_therapist_id == referral.accepted_therapist_id),
            notes=f"媒合轉入（派案碼 {referral.referral_code}）",
        )
        case_response = _create_case(case_body, user, db)
        case = db.query(Case).filter(Case.id == case_response.id).first()
        # 立刻把 converted_case_id 落地：萬一接下來建立 Appointment 失敗（如
        # 診間衝突），重試轉預約時要接回同一筆個案，不能再建第二筆重複的。
        referral.converted_case_id = case.id
        db.commit()
        db.refresh(referral)
        db.refresh(case)

    appt_body = AppointmentCreate(
        case_id=case.id,
        room_id=body.room_id,
        session_type=body.session_type,
        start_time=body.start_time,
        end_time=body.end_time,
        amount=body.amount,
        funding_source=body.funding_source,
        plan_id=body.plan_id,
    )
    appt_response = _create_appointment(appt_body, user, db)

    referral.appointment_id = appt_response.id
    referral.status = "booked"
    write_audit(db, "referrals", referral.id, "CONVERT", user.id, None,
                {"case_id": case.id, "appointment_id": appt_response.id})
    db.commit()
    db.refresh(referral)
    return referral


def mark_arrived(db: Session, user: User, referral: Referral, national_id: str | None, birth_date, phone: str | None) -> Referral:
    """初診有到：報到（沿用既有 check-in 端點寫入 session_record）＋
    產生病歷號（沿用既有 activate_case 兩段式編號）。個案轉「進行中」並
    自動出現在個案管理列表，媒合案本身則離開媒合列表。"""
    if referral.status != "booked":
        raise HTTPException(status_code=400, detail=f"目前狀態（{referral.status}）不是初診已預約")

    case = db.query(Case).filter(Case.id == referral.converted_case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="個案不存在")

    if national_id and not case.national_id_encrypted:
        case.national_id_encrypted = encrypt_national_id(national_id)
        case.national_id_hmac = hmac_national_id(national_id)
    if birth_date and not case.birth_date:
        case.birth_date = birth_date
    if phone and not case.phone:
        case.phone = phone
    db.flush()

    if case.status == "initial":
        _activate_case(case.id, user, db)

    _check_in(db, referral.appointment_id, CheckInRequest(status="arrived"), user)

    referral.status = "converted"
    referral.closed_at = datetime.now(timezone.utc)
    write_audit(db, "referrals", referral.id, "ARRIVED", user.id, None, {"case_id": case.id})
    db.commit()
    db.refresh(referral)
    return referral


def mark_no_show(db: Session, user: User, referral: Referral, reason: str, next_action: str) -> Referral:
    """初診未到：依勾選分流回「轉預約」（同一心理師重排）或「派案」
    （換人重新媒合），或直接轉媒合結案。"""
    if referral.status != "booked":
        raise HTTPException(status_code=400, detail=f"目前狀態（{referral.status}）不是初診已預約")
    if next_action not in ("rebook", "reassign", "close"):
        raise HTTPException(status_code=400, detail="next_action 必須是 rebook / reassign / close")

    _check_in(db, referral.appointment_id, CheckInRequest(status="no_show", no_show_reason=reason), user)

    if next_action == "rebook":
        referral.status = "accepted"
    elif next_action == "reassign":
        referral.status = "unmatched"
        referral.accepted_therapist_id = None
    else:
        referral.status = "closed"
        referral.close_reason = f"初診未到：{reason}"
        referral.closed_at = datetime.now(timezone.utc)
    write_audit(db, "referrals", referral.id, "NO_SHOW", user.id, None, {"reason": reason, "next_action": next_action})
    db.commit()
    db.refresh(referral)
    return referral
