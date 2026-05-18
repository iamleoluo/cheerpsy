import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.claim_batch import ClaimBatch
from app.models.institution import Institution
from app.models.invoice import Invoice
from app.models.petty_cash import PettyCash
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    if not rows:
        buf = io.StringIO()
        buf.write("")
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cases")
def export_cases(
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    cases = db.query(Case).order_by(Case.id).all()
    therapist_map = {u.id: u.name for u in db.query(User).all()}
    inst_map = {i.id: i.name for i in db.query(Institution).all()}

    rows = []
    for c in cases:
        rows.append({
            "ID": c.id,
            "案號": c.case_code or "",
            "正式案號": c.case_number or "",
            "計費週期": c.billing_cycle or "",
            "姓名": c.name,
            "性別": c.gender or "",
            "出生日期": str(c.birth_date) if c.birth_date else "",
            "手機": c.phone or "",
            "市話": c.phone_home or "",
            "地址": c.address or "",
            "緊急聯絡人": c.emergency_contact or "",
            "緊急電話1": c.emergency_phone or "",
            "緊急電話2": c.emergency_phone2 or "",
            "進案日": str(c.initial_visit_date) if c.initial_visit_date else "",
            "經費來源": "自費" if c.funding_source == "self_pay" else "機構",
            "機構名稱": inst_map.get(c.institution_id, "") if c.institution_id else "",
            "轉介來源": c.referral_source or "",
            "會談地點": c.session_location or "",
            "負責心理師": therapist_map.get(c.therapist_id, ""),
            "狀態": c.status,
            "備註": c.notes or "",
        })
    return _csv_response(rows, "cases.csv")


@router.get("/appointments")
def export_appointments(
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    appts = db.query(Appointment).order_by(Appointment.id).all()
    case_map = {c.id: c.name for c in db.query(Case).all()}
    therapist_map = {u.id: u.name for u in db.query(User).all()}
    room_map = {r.id: r.name for r in db.query(Room).all()}

    rows = []
    for a in appts:
        lower = a.time_range.lower if a.time_range else None
        upper = a.time_range.upper if a.time_range else None
        rows.append({
            "ID": a.id,
            "預約編號": a.appointment_number,
            "個案": case_map.get(a.case_id, ""),
            "心理師": therapist_map.get(a.therapist_id, ""),
            "空間": room_map.get(a.room_id, "") if a.room_id else "",
            "類型": a.session_type,
            "開始時間": str(lower) if lower else "",
            "結束時間": str(upper) if upper else "",
            "金額": float(a.amount),
            "狀態": a.status,
            "建立時間": str(a.created_at) if a.created_at else "",
        })
    return _csv_response(rows, "appointments.csv")


@router.get("/ledger")
def export_ledger(
    year: int | None = Query(None),
    month: int | None = Query(None),
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    q = db.query(SessionRecord)
    if year:
        q = q.filter(extract("year", SessionRecord.session_date) == year)
    if month:
        q = q.filter(extract("month", SessionRecord.session_date) == month)
    records = q.order_by(SessionRecord.session_date).all()

    therapist_map = {u.id: u.name for u in db.query(User).all()}
    case_map = {c.id: c.name for c in db.query(Case).all()}
    room_map = {r.id: r.name for r in db.query(Room).all()}

    rows = []
    for r in records:
        rows.append({
            "ID": r.id,
            "日期": str(r.session_date),
            "心理師": therapist_map.get(r.therapist_id, ""),
            "心理師ID": r.therapist_id,
            "個案": case_map.get(r.case_id, "") if r.case_id else "",
            "個案ID": r.case_id or "",
            "類型": r.session_type,
            "空間": room_map.get(r.room_id, "") if r.room_id else "",
            "費用類別": r.fee_category,
            "金額": float(r.amount),
            "折扣金額": float(r.discount_amount or 0),
            "折扣備註": r.discount_note or "",
            "實收金額": float(r.amount) - float(r.discount_amount or 0),
            "收款狀態": r.payment_status,
            "付款方式": r.payment_method or "",
            "付款備註": r.payment_note or "",
            "付款時間": r.paid_at.isoformat() if r.paid_at else "",
            "收據編號": r.receipt_no or "",
            "是否作廢": "是" if r.is_void else "否",
            "作廢原因": r.void_reason or "",
            "作廢時間": r.voided_at.isoformat() if r.voided_at else "",
            "作廢者ID": r.voided_by or "",
            "經費來源": r.funding_source or "",
            "抽成比例": float(r.commission_rate_used) if r.commission_rate_used else "",
            "核銷案ID": r.claim_batch_id or "",
            "請款單號": r.claim_number or "",
            "到款收據": r.receipt_number or "",
            "鎖定時間": str(r.locked_at) if r.locked_at else "",
            "預約ID": r.appointment_id or "",
        })
    return _csv_response(rows, "ledger.csv")


@router.get("/petty-cash")
def export_petty_cash(
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    records = db.query(PettyCash).order_by(PettyCash.date, PettyCash.id).all()
    rows = []
    for r in records:
        rows.append({
            "ID": r.id,
            "日期": str(r.date),
            "金額": float(r.amount),
            "類別": r.category,
            "說明": r.description or "",
            "收據備註": r.receipt_note or "",
            "餘額": float(r.balance_after),
        })
    return _csv_response(rows, "petty_cash.csv")


@router.get("/invoices")
def export_invoices(
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    invoices = db.query(Invoice).order_by(Invoice.id).all()
    rows = []
    for inv in invoices:
        rows.append({
            "ID": inv.id,
            "收據編號": inv.invoice_number,
            "預約ID": inv.appointment_id or "",
            "諮商ID": inv.session_id or "",
            "狀態": inv.status,
            "作廢原因": inv.void_reason or "",
            "建立時間": str(inv.created_at) if inv.created_at else "",
        })
    return _csv_response(rows, "invoices.csv")


@router.get("/users")
def export_users(
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.id).all()
    rows = []
    for u in users:
        rows.append({
            "ID": u.id,
            "Email": u.email,
            "姓名": u.name,
            "角色": u.role,
            "代碼": u.user_code or "",
            "啟用": "是" if u.is_active else "否",
            "抽成比例": float(u.commission_rate) if u.commission_rate else "",
            "預設價格": float(u.base_price) if u.base_price else "",
        })
    return _csv_response(rows, "users.csv")


@router.get("/rooms")
def export_rooms(
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    rooms = db.query(Room).order_by(Room.floor, Room.room_code).all()
    rows = []
    for r in rooms:
        rows.append({
            "ID": r.id,
            "名稱": r.name,
            "樓層": r.floor,
            "代碼": r.room_code,
            "特殊設備": "是" if r.has_special_equipment else "否",
            "備註": r.notes or "",
        })
    return _csv_response(rows, "rooms.csv")


@router.get("/institutions")
def export_institutions(
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    institutions = db.query(Institution).order_by(Institution.name).all()
    rows = []
    for i in institutions:
        rows.append({
            "ID": i.id,
            "機構名稱": i.name,
            "代號": i.code or "",
            "狀態": "啟用" if i.is_active else "已停用",
        })
    return _csv_response(rows, "institutions.csv")


@router.get("/claim-batches")
def export_claim_batches(
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    batches = db.query(ClaimBatch).order_by(ClaimBatch.id.desc()).all()
    rows = []
    for b in batches:
        rows.append({
            "ID": b.id,
            "編號": b.batch_number,
            "類型": b.type,
            "狀態": b.status,
            "個案ID": b.case_id or "",
            "機構ID": b.institution_id or "",
            "期間起": str(b.period_start) if b.period_start else "",
            "期間迄": str(b.period_end) if b.period_end else "",
            "金額": str(b.total_amount) if b.total_amount else "0",
            "外部參考": b.external_ref or "",
            "付款方式": b.payment_method or "",
            "付款備註": b.payment_note or "",
            "計費週期": b.billing_cycle or "",
            "預計次數": b.expected_sessions or "",
            "提交時間": b.submitted_at.isoformat() if b.submitted_at else "",
            "到款時間": b.received_at.isoformat() if b.received_at else "",
            "結清時間": b.closed_at.isoformat() if b.closed_at else "",
            "建立時間": str(b.created_at) if b.created_at else "",
        })
    return _csv_response(rows, "claim_batches.csv")


@router.get("/audit-log")
def export_audit_log(
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(5000).all()
    rows = []
    for lg in logs:
        rows.append({
            "ID": lg.id,
            "表": lg.table_name,
            "記錄ID": lg.record_id,
            "操作": lg.operation,
            "操作者ID": lg.changed_by or "",
            "時間": str(lg.changed_at) if lg.changed_at else "",
            "原因": lg.reason or "",
            "修改前": str(lg.before_data) if lg.before_data else "",
            "修改後": str(lg.after_data) if lg.after_data else "",
        })
    return _csv_response(rows, "audit_log.csv")


@router.get("/tables")
def list_exportable_tables(
    user: User = Depends(RequireRole(["admin"])),
):
    """List all tables available for CSV export."""
    return [
        {"key": "cases", "label": "個案", "endpoint": "/export/cases"},
        {"key": "appointments", "label": "預約", "endpoint": "/export/appointments"},
        {"key": "ledger", "label": "帳冊流水帳", "endpoint": "/export/ledger"},
        {"key": "claim-batches", "label": "核銷案", "endpoint": "/export/claim-batches"},
        {"key": "invoices", "label": "收據", "endpoint": "/export/invoices"},
        {"key": "petty-cash", "label": "零用金", "endpoint": "/export/petty-cash"},
        {"key": "users", "label": "使用者", "endpoint": "/export/users"},
        {"key": "rooms", "label": "諮商室", "endpoint": "/export/rooms"},
        {"key": "institutions", "label": "機構", "endpoint": "/export/institutions"},
        {"key": "audit-log", "label": "稽核日誌", "endpoint": "/export/audit-log"},
    ]
