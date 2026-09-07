"""媒合管理子系統的 API。行政端（媒合列表／媒合結案表／諮商需求表）與
心理師端（派案邀請：待回覆／已承接／已結束）都掛在這支路由裡——這是
一個小的子系統，兩邊操作的是同一份 referrals/referral_batches 資料，
分開成兩支檔案反而增加來回查找的成本。

依賴方向與 07 §3.2 一致：只有這裡（掛路由）與 app.main 允許
import app.referral.*，主系統其餘程式碼不會反過來 import 這裡。
"""

from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.institution import Institution
from app.models.user import User
from app.referral import service
from app.referral.models.batch import ReferralBatch, ReferralBatchMember
from app.referral.models.referral import Referral

router = APIRouter(prefix="/referrals", tags=["referrals"])

WRITE_ROLES = ["admin", "staff"]


# ─────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────

class ReferralCreate(BaseModel):
    name: str
    age: int | None = None
    gender: str | None = None
    phone: str | None = None
    mode: str = "in_person"
    institution_id: int | None = None
    funding_note: str | None = None
    issues: list[str] | None = None
    issue_note: str | None = None
    designated_therapist_id: int | None = None
    source: str | None = None
    availability: str | None = None
    note: str | None = None


class ReferralUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    gender: str | None = None
    phone: str | None = None
    mode: str | None = None
    institution_id: int | None = None
    funding_note: str | None = None
    issues: list[str] | None = None
    issue_note: str | None = None
    designated_therapist_id: int | None = None
    source: str | None = None
    availability: str | None = None
    note: str | None = None


class AssignRequest(BaseModel):
    therapist_ids: list[int]


class CancelRequest(BaseModel):
    reason: str


class ConvertRequest(BaseModel):
    room_id: int | None = None
    session_type: str = "in_person"
    start_time: datetime
    end_time: datetime
    amount: float | None = None
    funding_source: str = "self_pay"
    plan_id: int | None = None


class ArrivedRequest(BaseModel):
    national_id: str | None = None
    birth_date: date | None = None
    phone: str | None = None


class NoShowRequest(BaseModel):
    reason: str
    next_action: str  # rebook | reassign | close


class AcceptRequest(BaseModel):
    slots: list[str]


class DeclineRequest(BaseModel):
    reason: str


class BatchMemberResponse(BaseModel):
    id: int
    therapist_id: int
    therapist_name: str | None = None
    reply_status: str
    decline_reason: str | None = None
    proposed_slots: list[str] | None = None
    replied_at: datetime | None = None


class BatchResponse(BaseModel):
    id: int
    batch_seq: int
    is_open: bool
    sent_at: datetime | None = None
    members: list[BatchMemberResponse]


class ReferralResponse(BaseModel):
    id: int
    referral_code: str
    name: str
    age: int | None = None
    gender: str | None = None
    phone: str | None = None
    mode: str
    institution_id: int | None = None
    institution_name: str | None = None
    funding_note: str | None = None
    issues: list[str] | None = None
    issue_note: str | None = None
    designated_therapist_id: int | None = None
    designated_therapist_name: str | None = None
    source: str | None = None
    availability: str | None = None
    note: str | None = None
    status: str
    accepted_therapist_id: int | None = None
    accepted_therapist_name: str | None = None
    converted_case_id: int | None = None
    appointment_id: int | None = None
    close_reason: str | None = None
    closed_at: datetime | None = None
    created_at: datetime | None = None
    batches: list[BatchResponse]


def _member_to_response(m: ReferralBatchMember) -> BatchMemberResponse:
    return BatchMemberResponse(
        id=m.id,
        therapist_id=m.therapist_id,
        therapist_name=m.therapist.name if m.therapist else None,
        reply_status=m.reply_status,
        decline_reason=m.decline_reason,
        proposed_slots=json.loads(m.proposed_slots) if m.proposed_slots else None,
        replied_at=m.replied_at,
    )


def _batch_to_response(b: ReferralBatch) -> BatchResponse:
    return BatchResponse(
        id=b.id, batch_seq=b.batch_seq, is_open=b.is_open, sent_at=b.sent_at,
        members=[_member_to_response(m) for m in b.members],
    )


def _to_response(r: Referral) -> ReferralResponse:
    return ReferralResponse(
        id=r.id,
        referral_code=r.referral_code,
        name=r.name,
        age=r.age,
        gender=r.gender,
        phone=r.phone,
        mode=r.mode,
        institution_id=r.institution_id,
        institution_name=r.institution.name if r.institution else None,
        funding_note=r.funding_note,
        issues=json.loads(r.issues) if r.issues else None,
        issue_note=r.issue_note,
        designated_therapist_id=r.designated_therapist_id,
        designated_therapist_name=r.designated_therapist.name if r.designated_therapist else None,
        source=r.source,
        availability=r.availability,
        note=r.note,
        status=r.status,
        accepted_therapist_id=r.accepted_therapist_id,
        accepted_therapist_name=r.accepted_therapist.name if r.accepted_therapist else None,
        converted_case_id=r.converted_case_id,
        appointment_id=r.appointment_id,
        close_reason=r.close_reason,
        closed_at=r.closed_at,
        created_at=r.created_at,
        batches=[_batch_to_response(b) for b in r.batches],
    )


def _get_referral(db: Session, referral_id: int) -> Referral:
    r = db.query(Referral).filter(Referral.id == referral_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="找不到此媒合案")
    return r


# ─────────────────────────────────────────────────────────────────────────
# 行政端：媒合列表／媒合結案表／諮商需求表
# ─────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ReferralResponse])
def list_referrals(
    active_only: bool = Query(True, description="True=媒合列表（進行中）；False=媒合結案表（已轉個案/取消/結案）"),
    q: str | None = Query(None, description="搜尋姓名／電話／派案碼"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.process_timeouts(db)
    query = db.query(Referral)
    if active_only:
        query = query.filter(Referral.status.in_(service.ACTIVE_STATUSES))
    else:
        query = query.filter(Referral.status.in_(["converted", "cancelled", "closed"]))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Referral.name.ilike(like)) | (Referral.phone.ilike(like)) | (Referral.referral_code.ilike(like))
        )
    referrals = query.order_by(Referral.id.desc()).limit(300).all()
    return [_to_response(r) for r in referrals]


@router.get("/{referral_id}", response_model=ReferralResponse)
def get_referral(referral_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_response(_get_referral(db, referral_id))


@router.post("", response_model=ReferralResponse, status_code=201)
def create_referral(body: ReferralCreate, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    return _to_response(service.create_referral(db, user, body))


@router.put("/{referral_id}", response_model=ReferralResponse)
def update_referral(referral_id: int, body: ReferralUpdate, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    referral = _get_referral(db, referral_id)
    return _to_response(service.update_referral(db, user, referral, body))


@router.put("/{referral_id}/assign", response_model=ReferralResponse)
def assign_therapists(referral_id: int, body: AssignRequest, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    referral = _get_referral(db, referral_id)
    service.assign_therapists(db, user, referral, body.therapist_ids)
    db.refresh(referral)
    return _to_response(referral)


@router.put("/{referral_id}/cancel", response_model=ReferralResponse)
def cancel_referral(referral_id: int, body: CancelRequest, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    referral = _get_referral(db, referral_id)
    return _to_response(service.cancel_referral(db, user, referral, body.reason))


@router.put("/{referral_id}/convert", response_model=ReferralResponse)
def convert_to_appointment(referral_id: int, body: ConvertRequest, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    referral = _get_referral(db, referral_id)
    return _to_response(service.convert_to_appointment(db, user, referral, body))


@router.put("/{referral_id}/arrived", response_model=ReferralResponse)
def mark_arrived(referral_id: int, body: ArrivedRequest, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    referral = _get_referral(db, referral_id)
    return _to_response(service.mark_arrived(db, user, referral, body.national_id, body.birth_date, body.phone))


@router.put("/{referral_id}/no-show", response_model=ReferralResponse)
def mark_no_show(referral_id: int, body: NoShowRequest, user: User = Depends(RequireRole(WRITE_ROLES)), db: Session = Depends(get_db)):
    referral = _get_referral(db, referral_id)
    return _to_response(service.mark_no_show(db, user, referral, body.reason, body.next_action))


# ─────────────────────────────────────────────────────────────────────────
# 心理師端：派案邀請（待回覆／已承接／已結束）
# ─────────────────────────────────────────────────────────────────────────

class PoolInviteResponse(BaseModel):
    member_id: int
    referral_id: int
    referral_code: str
    name: str
    age: int | None = None
    gender: str | None = None
    mode: str
    issue_note: str | None = None
    issues: list[str] | None = None
    source: str | None = None
    is_dual_relationship_risk: bool = False
    availability: str | None = None
    designated_label: str  # "是（本人姓名）" / "不指定" / "指定心理師無法安排"
    other_pending_count: int  # 另有 N 位心理師評估中
    batch_seq: int
    sent_at: datetime | None = None
    reply_status: str
    decline_reason: str | None = None
    proposed_slots: list[str] | None = None


def _designated_label(referral: Referral, therapist_id: int) -> str:
    if referral.designated_therapist_id is None:
        return "不指定"
    if referral.designated_therapist_id == therapist_id:
        return f"是（{referral.designated_therapist.name if referral.designated_therapist else ''}）"
    return "指定心理師無法安排"


def _invite_to_response(m: ReferralBatchMember) -> PoolInviteResponse:
    batch = m.batch
    referral = batch.referral
    other_pending = sum(1 for x in batch.members if x.id != m.id and x.reply_status == "pending")
    return PoolInviteResponse(
        member_id=m.id,
        referral_id=referral.id,
        referral_code=referral.referral_code,
        name=referral.name,
        age=referral.age,
        gender=referral.gender,
        mode=referral.mode,
        issue_note=referral.issue_note,
        issues=json.loads(referral.issues) if referral.issues else None,
        source=referral.source,
        is_dual_relationship_risk=(referral.source == "親友介紹"),
        availability=referral.availability,
        designated_label=_designated_label(referral, m.therapist_id),
        other_pending_count=other_pending,
        batch_seq=batch.batch_seq,
        sent_at=batch.sent_at,
        reply_status=m.reply_status,
        decline_reason=m.decline_reason,
        proposed_slots=json.loads(m.proposed_slots) if m.proposed_slots else None,
    )


@router.get("/pool/pending", response_model=list[PoolInviteResponse])
def pool_pending(user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    service.process_timeouts(db)
    members = (
        db.query(ReferralBatchMember)
        .join(ReferralBatch)
        .filter(ReferralBatchMember.therapist_id == user.id, ReferralBatchMember.reply_status == "pending", ReferralBatch.is_open.is_(True))
        .order_by(ReferralBatchMember.id.desc())
        .all()
    )
    return [_invite_to_response(m) for m in members]


@router.get("/pool/accepted", response_model=list[PoolInviteResponse])
def pool_accepted(user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    members = (
        db.query(ReferralBatchMember)
        .filter(ReferralBatchMember.therapist_id == user.id, ReferralBatchMember.reply_status == "accepted")
        .order_by(ReferralBatchMember.id.desc())
        .all()
    )
    return [_invite_to_response(m) for m in members]


@router.get("/pool/history", response_model=list[PoolInviteResponse])
def pool_history(user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    members = (
        db.query(ReferralBatchMember)
        .filter(ReferralBatchMember.therapist_id == user.id, ReferralBatchMember.reply_status.in_(["declined", "superseded", "expired", "released"]))
        .order_by(ReferralBatchMember.id.desc())
        .limit(200)
        .all()
    )
    return [_invite_to_response(m) for m in members]


@router.put("/pool/{member_id}/accept", response_model=PoolInviteResponse)
def accept_invite(member_id: int, body: AcceptRequest, user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    member = service.accept_invite(db, user, member_id, body.slots)
    return _invite_to_response(member)


@router.put("/pool/{member_id}/decline", response_model=PoolInviteResponse)
def decline_invite(member_id: int, body: DeclineRequest, user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    member = service.decline_invite(db, user, member_id, body.reason)
    return _invite_to_response(member)


@router.put("/pool/{member_id}/release", response_model=PoolInviteResponse)
def release_invite(member_id: int, user: User = Depends(RequireRole(["therapist"])), db: Session = Depends(get_db)):
    member = service.release_invite(db, user, member_id)
    return _invite_to_response(member)
