"""診間日曆的聚合讀取端點 — V2升級計畫 02 §5.1。

為什麼要有這一支（而不是讓前端拿通用的 /appointments 自己算）：

**「整格轉灰」需要同時看四張表** —— appointments.check_in_status、
session_records.payment_status/copay_collected_at、receipts 是否存在、
appointment_admin_tasks 是否全勾。02 §6.1 的原話是「由聚合端點一次計算，
**不在前端拼湊**」，理由寫在 N+1 那一節：逐格查會是 4 × 60 筆/天 次查詢。

而且轉灰**不是一條規則，是三條**（02 §4.3 / 03 §整格轉灰時機）：

    自費需收款案   收款 ＋ 開立收據都完成才轉灰
    自費月結案     按完「已到」即轉灰（不需收款／收據）
    機構案         已到 ＋ 應收結清 ＋ 行政流程提醒**全部勾完**，三者皆滿足

把這三條放在前端，等於把「這格今天還要不要處理」的判斷散進畫面裡；放在這裡
則是一次 join 算完、前端只管畫色。
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.appointment_admin_task import AppointmentAdminTask
from app.models.receipt import Receipt
from app.models.session_record import SessionRecord
from app.models.user import User
from app.utils.tz import day_range_utc

router = APIRouter(prefix="/room-calendar", tags=["room-calendar"])


def _settled(
    appt: Appointment,
    billing_cycle: str | None,
    sr: SessionRecord | None,
    has_receipt: bool,
    pending_tasks: int,
) -> bool:
    """整格轉灰 —— 意思是「這格今天不用再碰了」，不是「已完成」。

    三條規則見模組 docstring。未到**不轉灰**（03：未到的格子維持紅底）。
    """
    if appt.check_in_status != "arrived":
        return False

    is_institution = bool(appt.plan_id) or (appt.funding_source == "institution")

    if is_institution:
        # 機構案：應收（個案自付額）結清 ＋ 行政流程提醒全勾。
        # 自付額為 0 的全額補助方案視為已結清。
        due = float(sr.case_payable if sr and sr.case_payable is not None else 0)
        collected = bool(sr and sr.copay_collected_at) or due <= 0
        return collected and pending_tasks == 0

    if billing_cycle == "monthly":
        # 自費月結：按完已到即轉灰，不需收款／收據（記入當月月結帳）。
        return True

    # 自費需收款（次結／多次結）：收款＋開據都完成。
    return bool(sr and sr.copay_collected_at) and has_receipt


@router.get("")
def room_calendar(
    q: date = Query(..., description="台北時區日期"),
    floor: str = Query("all", description="all / 1 / 2 / 3"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """回傳當日每一筆預約，每格**已算好** is_settled / admin_tasks_pending / quota_label。

    刻意**不做**任何寫入。02 §4.1 已裁示 materialize_due_appointments 只能由
    行政手動觸發，讀取端點不得順手結算（那正是先前 /ledger 五個 GET 犯的錯）。
    """
    start, end = day_range_utc(q)

    appts: list[Appointment] = (
        db.query(Appointment)
        .options(
            joinedload(Appointment.case),
            joinedload(Appointment.therapist),
            joinedload(Appointment.room),
        )
        .filter(
            Appointment.status != "cancelled",
            func.upper(Appointment.time_range) > start,
            func.lower(Appointment.time_range) < end,
        )
        .all()
    )
    if not appts:
        return {"date": str(q), "cells": [], "summary": _summary([])}

    ids = [a.id for a in appts]

    # ── 一次撈完四張表，不逐格查（02 §6.1 的 N+1 對策）────────────────
    sr_by_appt: dict[int, SessionRecord] = {
        r.appointment_id: r
        for r in db.query(SessionRecord)
        .filter(SessionRecord.appointment_id.in_(ids), SessionRecord.is_void.is_(False))
        .all()
        if r.appointment_id
    }
    receipt_sr_ids = {
        r[0]
        for r in db.query(Receipt.session_record_id)
        .filter(
            Receipt.session_record_id.in_([s.id for s in sr_by_appt.values()] or [0]),
            Receipt.status == "issued",
        )
        .all()
    }
    pending_by_appt: dict[int, int] = dict(
        db.query(AppointmentAdminTask.appointment_id, func.count(AppointmentAdminTask.id))
        .filter(
            AppointmentAdminTask.appointment_id.in_(ids),
            AppointmentAdminTask.is_done.is_(False),
        )
        .group_by(AppointmentAdminTask.appointment_id)
        .all()
    )

    cells = []
    for a in appts:
        if floor != "all" and a.room and str(a.room.floor) != floor:
            continue

        sr = sr_by_appt.get(a.id)
        has_receipt = bool(sr and sr.id in receipt_sr_ids)
        pending = pending_by_appt.get(a.id, 0)
        case = a.case
        billing_cycle = case.billing_cycle if case else None

        quote = a.plan_quote or {}
        quota = quote.get("quota") or {}
        # 額度三態在快照裡是巢狀的：quota.before.{used,booked,reserved,limit}。
        # 標籤沿用 07 adapter 的算法「已用＋已預約 / 上限」，也就是 v7 格子上
        # 看到的「青壯 2/3」。
        before = quota.get("before") or {}
        used, booked, limit = before.get("used"), before.get("booked") or 0, before.get("limit")
        quota_label = f"{used + booked}/{limit}" if used is not None and limit is not None else None

        cells.append(
            {
                # id 與 appointment_id 同值：前者給沿用 /appointments 欄位名的
                # CheckInPanel，後者是這支端點自己的語意。
                "id": a.id,
                "appointment_id": a.id,
                "appointment_number": a.appointment_number,
                "room_id": a.room_id,
                "room_name": a.room.name if a.room else None,
                "start_time": a.time_range.lower.isoformat() if a.time_range else None,
                "end_time": a.time_range.upper.isoformat() if a.time_range else None,
                "case_id": a.case_id,
                "case_name": case.name if case else None,
                "case_number": case.case_number if case else None,
                "gender": case.gender if case else None,
                "is_couple": bool(a.couple_case_id) or (case.case_type == "couple" if case else False),
                "therapist_name": a.therapist.name if a.therapist else None,
                "session_type": a.session_type,
                "billing_cycle": billing_cycle,
                "plan_name": quote.get("plan_name"),
                "amount": float(a.amount or 0),
                "case_payable": float(sr.case_payable) if sr and sr.case_payable is not None else None,
                "institution_payable": (
                    float(sr.institution_payable) if sr and sr.institution_payable is not None else None
                ),
                "check_in_status": a.check_in_status,
                "checked_in_at": a.checked_in_at.isoformat() if a.checked_in_at else None,
                "no_show_reason": a.no_show_reason,
                "no_show_note": a.no_show_note,
                "no_show_followup": a.no_show_followup,
                "copay_payment_method": sr.copay_payment_method if sr else None,
                # CheckInPanel 需要的幾個原始欄位（它是同一格點開的明細視窗）
                "therapist_id": a.therapist_id,
                "funding_source": a.funding_source,
                "status": a.status,
                "couple_name": a.couple_case.name if a.couple_case_id and a.couple_case else None,
                "copay_collected_at": sr.copay_collected_at.isoformat() if sr and sr.copay_collected_at else None,
                # 已開立的收據（receipts 表），**不是** session_records.receipt_no
                # ——後者是建立場次時就預配好的號碼，跟收款與否無關。
                "issued_receipt_no": _issued_no(db, sr) if has_receipt else None,
                # CheckInPanel 沿用 /appointments 的欄位名，而那支本來就是回
                # receipts 表的號碼（appointments.py:106），所以這裡給同一個值。
                "receipt_no": _issued_no(db, sr) if has_receipt else None,
                # ── 前端只管畫色的三個欄位 ────────────────────────────
                "is_settled": _settled(a, billing_cycle, sr, has_receipt, pending),
                "admin_tasks_pending": pending,
                "quota_label": quota_label,
                # 機構額度剩最後一次 → 整格標黃，避免收錯金額（v7 定案 ⑤）
                "is_last_quota": bool(quota.get("is_last")),
            }
        )

    return {"date": str(q), "cells": cells, "summary": _summary(cells)}


def _issued_no(db: Session, sr: SessionRecord | None) -> str | None:
    if not sr:
        return None
    r = (
        db.query(Receipt)
        .filter(Receipt.session_record_id == sr.id, Receipt.status == "issued")
        .first()
    )
    return r.receipt_no if r else None


def _summary(cells: list[dict]) -> dict:
    """頂部即時統計（v7 診間日曆）：應到 / 已報到 / 未到 / 待報到 / 已收 / 待收。"""
    arrived = sum(1 for c in cells if c["check_in_status"] == "arrived")
    no_show = sum(1 for c in cells if c["check_in_status"] == "no_show")
    pending = sum(1 for c in cells if c["check_in_status"] == "pending")
    collected = sum(
        (c["case_payable"] if c["case_payable"] is not None else c["amount"])
        for c in cells
        if c["copay_collected_at"]
    )
    due = sum(
        (c["case_payable"] if c["case_payable"] is not None else c["amount"])
        for c in cells
        if c["check_in_status"] == "arrived" and not c["copay_collected_at"]
    )
    return {
        "total": len(cells),
        "arrived": arrived,
        "no_show": no_show,
        "pending": pending,
        "collected": collected,
        "due": due,
        "unsettled": sum(1 for c in cells if not c["is_settled"]),
    }
