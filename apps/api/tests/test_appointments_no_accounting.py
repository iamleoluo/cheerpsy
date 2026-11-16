"""帳務拆除「上線 A」：預約流程不再寫帳務，但診間衝突檢查與取消照常運作。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.session_record import SessionRecord


@pytest.fixture()
def w(make_user, make_case, room):
    t = make_user("therapist", name="林心理師")
    staff = make_user("staff")
    admin = make_user("admin")
    case = make_case(t, "王小明")
    case2 = make_case(t, "李小華")
    return dict(t=t, staff=staff, admin=admin, case=case, case2=case2, room=room)


def _sr_count(db) -> int:
    return db.execute(text("SELECT count(*) FROM session_records")).scalar()


def _slot(days=3, hour=10, hours=1):
    start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    return start, start + timedelta(hours=hours)


def _create(client, auth, who, case, room, start, end, **extra):
    body = {"case_id": case.id, "room_id": room.id, "session_type": "in_person", "amount": 1000,
            "start_time": start.isoformat(), "end_time": end.isoformat(), **extra}
    return client.post("/appointments", json=body, headers=auth(who))


# ---- 建立：金額只是一個選填的數字（admin／staff 才存），沒有任何記帳 --------------
def test_create_self_pay_defaults_and_no_accounting_fields(client, auth, db, w):
    s, e = _slot()
    r = _create(client, auth, w["staff"], w["case"], w["room"], s, e)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["funding_source"] == "self_pay" and body["quota_id"] is None
    assert body["therapist_share"] is None and body["clinic_share"] is None  # 分潤屬已移除的記帳
    assert db.execute(text("SELECT count(*) FROM session_records")).scalar() == 0


def test_amount_stored_for_whoever_creates_and_validated(client, auth, db, w):
    s, e = _slot()
    # 隔離的單位是心理師不是欄位：心理師建立自己的預約，金額照存、回應回真實值
    r = _create(client, auth, w["t"], w["case"], w["room"], s, e, amount=999)
    assert r.status_code == 201 and r.json()["amount"] == 999
    assert float(db.execute(text("SELECT amount FROM appointments WHERE id=:i"), {"i": r.json()["id"]}).scalar()) == 999
    s2, e2 = _slot(5)
    assert _create(client, auth, w["admin"], w["case"], w["room"], s2, e2, amount=1800.5).json()["amount"] == 1800.5
    for bad in (-1, 10_000_000):
        assert _create(client, auth, w["staff"], w["case"], w["room"], *_slot(6), amount=bad).status_code == 422


def test_edit_amount_visible_to_admin_staff_and_owner_and_audited(client, auth, db, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"amount": 2200})
    assert r.status_code == 200 and r.json()["amount"] == 2200
    assert client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"room_id": w["room"].id}).json()["amount"] == 2200  # 沒送就不改
    assert client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"amount": 0}).status_code == 422  # 金額必須大於 0
    assert client.put(f"/appointments/{a['id']}", headers=auth(w["staff"]), json={"amount": -5}).status_code == 422
    client.put(f"/appointments/{a['id']}", headers=auth(w["admin"]), json={"amount": 3000})
    assert client.get(f"/appointments/{a['id']}", headers=auth(w["admin"])).json()["amount"] == 3000
    assert client.get(f"/appointments/{a['id']}", headers=auth(w["t"])).json()["amount"] == 3000  # 自己的預約：真實金額
    assert client.get("/appointments", headers=auth(w["t"])).json()[0]["amount"] == 3000
    assert client.get("/appointments", headers=auth(w["staff"])).json()[0]["amount"] == 3000
    assert client.put(f"/appointments/{a['id']}", headers=auth(w["t"]), json={"amount": 1}).json()["amount"] == 1  # 自己的可改
    n = db.execute(text("SELECT count(*) FROM audit_log WHERE table_name='appointments' AND record_id=:i AND operation='UPDATE'"),
                   {"i": a["id"]}).scalar()
    assert n >= 3  # 金額改動有稽核


def test_batch_create_amount_applies_to_all_slots_and_conflict(client, auth, db, w):
    s, e = _slot()
    slots = [{"start_time": s.isoformat(), "end_time": e.isoformat(), "amount": 3000},
             {"start_time": (s + timedelta(days=7)).isoformat(),
              "end_time": (e + timedelta(days=7)).isoformat()}]
    body = {"case_id": w["case"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
            "amount": 2000, "funding_source": "institution", "slots": slots}
    r = client.post("/appointments/batch", json=body, headers=auth(w["staff"]))
    assert r.status_code == 201, r.text
    assert all(x["amount"] == 2000 for x in r.json())  # 整批同一個金額；slot 上的 amount 忽略
    # 同一批次再送一次：第一個 slot 就衝突，整批 409
    r2 = client.post("/appointments/batch", json=body, headers=auth(w["staff"]))
    assert r2.status_code == 409


# ---- 診間重疊仍回 409 -------------------------------------------------------
def test_room_overlap_409_on_create(client, auth, w):
    s, e = _slot()
    assert _create(client, auth, w["staff"], w["case"], w["room"], s, e).status_code == 201
    r = _create(client, auth, w["staff"], w["case2"], w["room"],
                s + timedelta(minutes=30), e + timedelta(minutes=30))
    assert r.status_code == 409
    assert "王小明" not in r.text  # 衝突訊息不洩漏另一位個案姓名


def test_adjacent_slot_is_allowed(client, auth, w):
    s, e = _slot()
    assert _create(client, auth, w["staff"], w["case"], w["room"], s, e).status_code == 201
    assert _create(client, auth, w["staff"], w["case2"], w["room"], e, e + timedelta(hours=1)).status_code == 201


def test_room_overlap_409_on_reschedule(client, auth, w):
    s, e = _slot()
    _create(client, auth, w["staff"], w["case"], w["room"], s, e)
    s2, e2 = _slot(hour=14)
    b = _create(client, auth, w["staff"], w["case2"], w["room"], s2, e2).json()
    r = client.put(f"/appointments/{b['id']}", headers=auth(w["staff"]),
                   json={"start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 409


def test_online_session_does_not_need_room(client, auth, w):
    s, e = _slot()
    r = client.post("/appointments", headers=auth(w["staff"]),
                    json={"case_id": w["case"].id, "session_type": "online", "amount": 1000,
                          "start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 201


def test_in_person_requires_room(client, auth, w):
    s, e = _slot()
    r = client.post("/appointments", headers=auth(w["staff"]),
                    json={"case_id": w["case"].id, "session_type": "in_person", "amount": 1000,
                          "start_time": s.isoformat(), "end_time": e.isoformat()})
    assert r.status_code == 400


# ---- 報到／未到：不寫帳務 ---------------------------------------------------
def test_arrive_does_not_create_session_record(client, auth, db, w):
    s, e = _slot(days=0, hour=9)
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    before = _sr_count(db)
    r = client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "executed" and r.json()["checkin_status"] == "arrived"
    assert _sr_count(db) == before == 0
    assert db.query(SessionRecord).count() == 0


def test_absent_marks_no_show_without_fee_or_record(client, auth, db, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}/absent", headers=auth(w["staff"]),
                   json={"no_show_type": "no_notice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "no_show" and body["no_show_type"] == "no_notice"
    assert "no_show_fee" not in body  # 失約費功能已停用（欄位保留，一律 0）
    assert db.execute(text("SELECT no_show_fee FROM appointments WHERE id=:i"), {"i": a["id"]}).scalar() == 0
    assert _sr_count(db) == 0


def test_absent_rejects_unknown_type(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}/absent", headers=auth(w["staff"]), json={"no_show_type": "x"})
    assert r.status_code == 400


def test_arrive_twice_rejected(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"])).status_code == 200
    assert client.put(f"/appointments/{a['id']}/arrive", headers=auth(w["staff"])).status_code == 400


# ---- 打開 /ledger 不會再改寫預約 --------------------------------------------
def test_ledger_reads_do_not_materialize_past_appointments(client, auth, db, w, make_appt):
    past = datetime.now(timezone.utc) - timedelta(days=2)
    a = make_appt(w["case"], w["t"], w["room"], start=past)  # booked，已過期
    for path in ("/ledger", "/ledger/pending-docs", "/ledger/confirmed-docs",
                 "/ledger/self-pay-unpaid", "/ledger/self-pay-all", "/ledger/self-pay-cases"):
        assert client.get(path, headers=auth(w["admin"])).status_code == 200, path
    db.expire_all()
    assert db.execute(text("SELECT status FROM appointments WHERE id=:i"), {"i": a.id}).scalar() == "booked"
    assert _sr_count(db) == 0


def test_ledger_settle_is_gone(client, auth, w):
    assert client.post("/ledger/settle", json={}, headers=auth(w["admin"])).status_code == 410


# ---- 410：金額與付款方式 ----------------------------------------------------
def test_amount_endpoint_gone_payment_endpoint_restored(client, auth, db, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e, amount=900).json()
    assert client.put(f"/appointments/{a['id']}/amount", headers=auth(w["admin"]),
                      json={"amount": 999}).status_code == 410  # 專屬金額端點仍停用（金額走預約編輯）
    # 付款方式（自費／機構、額度）屬金流資訊，已恢復；機構案沒有額度只警告
    r = client.put(f"/appointments/{a['id']}/payment", headers=auth(w["staff"]),
                   json={"funding_source": "institution", "amount": 900})
    assert r.status_code == 200 and r.json()["funding_source"] == "institution" and r.json()["warnings"]
    assert client.put(f"/appointments/{a['id']}/payment", headers=auth(w["t"]),
                      json={"funding_source": "self_pay"}).status_code == 403  # 改付款方式限行政
    # 不產生任何帳務紀錄
    assert db.execute(text("SELECT count(*) FROM session_records")).scalar() == 0


# ---- 取消 -------------------------------------------------------------------
def test_cancel_frees_room_for_rebooking(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"]))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert _create(client, auth, w["staff"], w["case2"], w["room"], s, e).status_code == 201


def test_therapist_can_cancel_own_but_not_others(client, auth, make_user, w):
    other = make_user("therapist")
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(other)).status_code == 404
    assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["t"])).status_code == 200


def test_cancel_past_cutoff_rejected(client, auth, w, make_appt):
    # 1 小時的場次 50 分鐘前開始：10 分鐘後結束，已過「結束前 20 分鐘」的取消時限
    soon = datetime.now(timezone.utc) - timedelta(minutes=50)
    a = make_appt(w["case"], w["t"], w["room"], start=soon)
    assert client.put(f"/appointments/{a.id}/cancel", headers=auth(w["staff"])).status_code == 400


def test_cannot_cancel_twice(client, auth, w):
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"])).status_code == 200
    assert client.put(f"/appointments/{a['id']}/cancel", headers=auth(w["staff"])).status_code == 400


# ---- 結案不再動額度，仍取消未來預約 ----------------------------------------
def test_close_case_cancels_future_appointments(client, auth, db, w):
    from app.auth.password import hash_password

    w["admin"].password_hash = hash_password("pw12345")
    db.commit()
    s, e = _slot()
    a = _create(client, auth, w["staff"], w["case"], w["room"], s, e).json()
    r = client.post(f"/cases/{w['case'].id}/close", headers=auth(w["admin"]),
                    json={"password": "pw12345", "reason": "測試"})
    assert r.status_code == 200, r.text
    assert client.get(f"/appointments/{a['id']}", headers=auth(w["admin"])).json()["status"] == "cancelled"


# ---- 儀表板不依賴帳務 -------------------------------------------------------
FORBIDDEN_KEYS = {"total_revenue", "unpaid_count", "unpaid_amount", "petty_balance", "petty_alert",
                  "session_count"}


def test_dashboard_payload_has_no_accounting(client, auth, w):
    for who in ("staff", "admin", "t"):
        r = client.get("/dashboard", headers=auth(w[who]))
        assert r.status_code == 200
        assert not (FORBIDDEN_KEYS & set(r.json()))


def test_dashboard_does_not_import_accounting_models():
    import app.routers.dashboard as d

    src = open(d.__file__, encoding="utf-8").read()
    for name in ("SessionRecord", "PettyCash", "session_record", "petty_cash"):
        assert f"import {name}" not in src and f"models.{name}" not in src


def test_dashboard_counts(client, auth, w, make_appt):
    make_appt(w["case"], w["t"], w["room"], start=datetime.now(timezone.utc) + timedelta(days=1))
    r = client.get("/dashboard", headers=auth(w["staff"])).json()
    assert r["active_cases"] == 2
    assert r["churn_count"] == 1  # case2 從未有預約，case 有未來預約
    assert r["new_referrals_month"] == 0 and r["matching_count"] == 0
    assert r["upcoming_reminders"] == 1


def test_dashboard_therapist_scoped_and_hides_clinic_stats(client, auth, make_user, w, make_appt):
    other = make_user("therapist")
    make_appt(w["case"], w["t"], w["room"], start=datetime.now(timezone.utc) + timedelta(days=1))
    r = client.get("/dashboard", headers=auth(other)).json()
    assert r["active_cases"] == 0 and r["upcoming_reminders"] == 0
    mine = client.get("/dashboard", headers=auth(w["t"])).json()
    assert mine["active_cases"] == 2 and mine["upcoming_reminders"] == 1
    assert mine["churn_count"] is None and mine["matching_count"] is None


def test_dashboard_today_counts(client, auth, w, make_appt):
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).replace(hour=15, minute=0, second=0, microsecond=0)
    a1 = make_appt(w["case"], w["t"], w["room"], start=today)
    a2 = make_appt(w["case2"], w["t"], w["room"], start=today + timedelta(hours=2))
    client.put(f"/appointments/{a1.id}/arrive", headers=auth(w["staff"]))
    client.put(f"/appointments/{a2.id}/absent", headers=auth(w["staff"]), json={"no_show_type": "no_notice"})
    r = client.get("/dashboard", headers=auth(w["staff"])).json()
    assert (r["today_expected"], r["today_arrived"], r["today_absent"]) == (2, 1, 1)


# ---- 媒合轉初診仍擋診間衝突；自費要填金額 ---------------------------------
def test_referral_convert_self_pay_needs_amount_and_room_conflict(client, auth, db, w):
    from datetime import date as _d
    from app.models.referral import (ReferralDispatch, ReferralDispatchTarget,
                                     ReferralRequest, ReferralSlotOffer)

    r = ReferralRequest(dispatch_code="261116009", name="新個案", consultation_mode="individual",
                        status="converted")
    db.add(r)
    db.flush()
    d = ReferralDispatch(referral_id=r.id, seq=1)
    db.add(d)
    db.flush()
    t = ReferralDispatchTarget(dispatch_id=d.id, therapist_id=w["t"].id, status="accepted")
    db.add(t)
    db.flush()
    day = _d.today() + timedelta(days=5)
    slot = ReferralSlotOffer(target_id=t.id, seq=1, slot_date=day, start_time="10:00", end_time="11:00")
    db.add(slot)
    db.commit()

    # 先在同診間同時段放一筆預約
    start = datetime.fromisoformat(f"{day}T10:00:00+08:00")
    first = _create(client, auth, w["staff"], w["case"], w["room"], start, start + timedelta(hours=1))
    assert first.status_code == 201
    r1 = client.post(f"/referrals/{r.id}/convert", headers=auth(w["staff"]),
                     json={"slot_id": slot.id, "room_id": w["room"].id})
    assert r1.status_code == 409

    # 同一位心理師同時段也不能再有第二筆（心理師衝突）：先取消原預約，再測線上場次
    assert client.put(f"/appointments/{first.json()['id']}/cancel", headers=auth(w["staff"])).status_code == 200
    # 換成線上場次：自費初診必填金額（機構案由方案帶出）
    r2 = client.post(f"/referrals/{r.id}/convert", headers=auth(w["staff"]),
                     json={"slot_id": slot.id, "session_type": "online"})
    assert r2.status_code == 422, r2.text
    r3 = client.post(f"/referrals/{r.id}/convert", headers=auth(w["staff"]),
                     json={"slot_id": slot.id, "session_type": "online", "amount": 1200})
    assert r3.status_code == 201, r3.text
    row = db.execute(text("SELECT amount, self_pay_amount FROM appointments WHERE id=:i"),
                     {"i": r3.json()["appointment_id"]}).one()
    assert float(row.amount) == 1200 and float(row.self_pay_amount) == 1200
