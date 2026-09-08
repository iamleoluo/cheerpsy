"""額度三態恆等式的守門測試（07 §4.1、models/enrollment.py:7-13）：

    quota_limit + extended_count == used_count + reserved_count + COUNT(booked)

這條恆等式原本有三個破口，每一個都會讓合約面板的三色長條慢慢對不起來，
而且錯得不明顯——長條看起來還是有值，只是數字愈來愈小/愈來愈大：

  ① 取消預約沒有還額度（reserve() 扣過，取消時沒人加回去）
  ② 刪除預約同上
  ③ 未到的預約被重複計算：release() 把它加回 reserved，但它的 status
     仍是 booked，booked 計數又數了它一次

這支測試針對三個破口各驗一次，並且每次都直接驗恆等式本身。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.institution.adapter import InstitutionFundingProvider
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.institution import Institution
from app.models.room import Room
from app.models.user import User

client = TestClient(app)
provider = InstitutionFundingProvider()

QUOTA_LIMIT = 6


def _seed(db, no_show_fee=None):
    admin = User(email="qi_admin@test.local", password_hash=hash_password("x"),
                 name="額度測試管理員", role="admin", user_code="A960")
    therapist = User(email="qi_t@test.local", password_hash=hash_password("x"),
                     name="額度測試心理師", role="therapist", user_code="T960",
                     commission_rate=Decimal("0.70"))
    db.add_all([admin, therapist])
    db.flush()
    inst = Institution(name="額度測試機構")
    db.add(inst)
    db.flush()
    room = Room(name="qi room", floor=1, room_code="QI-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()
    case = Case(name="額度測試個案", therapist_id=therapist.id, funding_source="institution",
                institution_id=inst.id, status="ongoing", case_number="99QI00001")
    db.add(case)
    db.flush()
    contract = InstContract(institution_id=inst.id, name="額度測試合約", created_by=admin.id)
    db.add(contract)
    db.flush()
    plan = InstPlan(contract_id=contract.id, name="額度測試方案", quota_unit="count",
                    default_quota_limit_numeric=QUOTA_LIMIT, compensation_mode="commission",
                    claim_group_key="額度測試", no_show_fee_numeric=no_show_fee, created_by=admin.id)
    db.add(plan)
    db.flush()
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=200, label="固定價"))
    db.flush()
    provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
    db.commit()
    return {
        "admin": admin, "therapist": therapist, "case": case, "plan": plan, "room": room,
        "token": create_access_token({"sub": str(admin.id), "role": "admin", "name": admin.name}),
    }


def _headers(ctx):
    return {"Authorization": f"Bearer {ctx['token']}"}


def _book(ctx, days_offset):
    start = datetime.now(timezone.utc) + timedelta(days=days_offset)
    end = start + timedelta(hours=1)
    r = client.post("/appointments", headers=_headers(ctx), json={
        "case_id": ctx["case"].id, "room_id": ctx["room"].id, "session_type": "in_person",
        "start_time": start.isoformat(), "end_time": end.isoformat(), "plan_id": ctx["plan"].id,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _assert_identity(db, ctx):
    """恆等式：上限 + 延長 == 已使用 + 已預留 + 已預約。"""
    db.expire_all()
    e = db.query(InstEnrollment).filter(
        InstEnrollment.case_id == ctx["case"].id, InstEnrollment.plan_id == ctx["plan"].id
    ).first()
    booked = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.plan_id == ctx["plan"].id,
            Appointment.case_id == ctx["case"].id,
            Appointment.status == "booked",
            Appointment.check_in_status != "no_show",
        )
        .scalar() or 0
    )
    left = float(e.quota_limit or 0) + float(e.extended_count or 0)
    right = float(e.used_count or 0) + float(e.reserved_count or 0) + booked
    assert left == right, (
        f"三態恆等式破了：limit({e.quota_limit}) + extended({e.extended_count}) "
        f"!= used({e.used_count}) + reserved({e.reserved_count}) + booked({booked})"
    )
    return e


class TestCancelReturnsQuota:
    def test_cancel_restores_reserved(self, db, http_db):
        ctx = _seed(db)
        _assert_identity(db, ctx)
        appt_id = _book(ctx, days_offset=3)
        e = _assert_identity(db, ctx)
        assert e.reserved_count == QUOTA_LIMIT - 1, "建立預約應把一格從 reserved 移到 booked"

        r = client.put(f"/appointments/{appt_id}/cancel", headers=_headers(ctx))
        assert r.status_code == 200, r.text
        e = _assert_identity(db, ctx)
        assert e.reserved_count == QUOTA_LIMIT, "取消後那一格要還回 reserved"

    def test_cancel_does_not_bill_no_show_fee(self, db, http_db):
        """未到補助補的是「個案沒出現」，取消不算——不可以因為取消就跟機構請款。"""
        from app.models.session_record import SessionRecord
        ctx = _seed(db, no_show_fee=800)
        appt_id = _book(ctx, days_offset=3)
        client.put(f"/appointments/{appt_id}/cancel", headers=_headers(ctx))
        fee_rows = db.query(SessionRecord).filter(
            SessionRecord.appointment_id == appt_id, SessionRecord.fee_category == "no_show_fee"
        ).count()
        assert fee_rows == 0, "取消預約不該產生未到補助的請款紀錄"


class TestDeleteReturnsQuota:
    def test_delete_restores_reserved(self, db, http_db):
        ctx = _seed(db)
        appt_id = _book(ctx, days_offset=3)
        r = client.request("DELETE", "/appointments", headers=_headers(ctx), json={"ids": [appt_id]})
        assert r.status_code == 200, r.text
        e = _assert_identity(db, ctx)
        assert e.reserved_count == QUOTA_LIMIT


class TestNoShowNotDoubleCounted:
    def test_no_show_keeps_identity(self, db, http_db):
        """未到的預約 status 仍是 booked（01 §C3 定案），但額度已經還進 reserved，
        所以 booked 計數必須排除它，否則同一格被算兩次。"""
        ctx = _seed(db)
        appt_id = _book(ctx, days_offset=-1)  # 過去的預約才能報到
        r = client.put(f"/appointments/{appt_id}/check-in", headers=_headers(ctx),
                       json={"status": "no_show", "no_show_reason": "unreachable"})
        assert r.status_code == 200, r.text

        appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
        db.refresh(appt)
        assert appt.status == "booked", "01 §C3：未到不轉 cancelled"
        assert appt.check_in_status == "no_show"

        e = _assert_identity(db, ctx)
        assert e.reserved_count == QUOTA_LIMIT, "未到後額度應完整還原，一次都沒用掉"
        assert e.used_count == 0

    def test_quote_after_no_show_still_shows_full_quota(self, db, http_db):
        """畫面上的「已用 N/M」是從 quote 出來的，未到之後不可以憑空少一格。"""
        from app.funding.dto import QuoteRequest
        ctx = _seed(db)
        appt_id = _book(ctx, days_offset=-1)
        client.put(f"/appointments/{appt_id}/check-in", headers=_headers(ctx),
                   json={"status": "no_show", "no_show_reason": "case_leave"})
        db.expire_all()
        quote = provider.quote(db, QuoteRequest(
            case_id=ctx["case"].id, plan_id=ctx["plan"].id, therapist_id=ctx["therapist"].id,
            session_type="in_person", visit_seq=2, duration_min=60,
            appt_date=datetime.now(timezone.utc).date(),
        ))
        assert quote.quota.before.used == 0
        assert quote.quota.before.booked == 0, "未到的那筆不可以還被算成已預約"
        assert quote.quota.before.reserved == QUOTA_LIMIT


class TestCloseCaseClosesEnrollments:
    def test_close_case_closes_institution_enrollment(self, db, http_db):
        ctx = _seed(db)
        _book(ctx, days_offset=3)
        r = client.post(f"/cases/{ctx['case'].id}/close", headers=_headers(ctx),
                        json={"password": "x", "reason": "測試結案"})
        assert r.status_code == 200, r.text
        db.expire_all()
        e = db.query(InstEnrollment).filter(InstEnrollment.case_id == ctx["case"].id).first()
        assert e.status == "closed", "結案後機構方案要一起關，不能還掛著 active"
        assert e.reserved_count == 0, "已預留全數釋出回方案總池"
        assert float(e.quota_limit) == float(e.used_count), "上限鎖在目前已使用量"


class TestVoidReturnsQuotaAndPool:
    def test_void_record_unconsumes(self, db, http_db):
        """作廢帳冊紀錄＝這場不算數，個案額度與合約額度池都要退回去。"""
        from app.institution.models.quota_pool import InstQuotaPool
        from app.models.session_record import SessionRecord

        ctx = _seed(db)
        # 掛一個金額型額度池到方案上，才驗得到池的回退
        pool = InstQuotaPool(contract_id=ctx["plan"].contract_id, name="額度測試池",
                             unit="amount", total_limit=Decimal("100000"), consumed_total=Decimal("0"))
        db.add(pool)
        db.flush()
        ctx["plan"].quota_pool_id = pool.id
        db.commit()

        appt_id = _book(ctx, days_offset=-1)
        r = client.put(f"/appointments/{appt_id}/check-in", headers=_headers(ctx), json={"status": "arrived"})
        assert r.status_code == 200, r.text
        db.expire_all()
        e = _assert_identity(db, ctx)
        assert e.used_count == 1
        db.refresh(pool)
        assert float(pool.consumed_total) == 1400.0, "報到時池要扣掉機構應付的 1400"

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        rv = client.put(f"/ledger/{sr.id}/void", headers=_headers(ctx), json={"reason": "誤登"})
        assert rv.status_code == 200, rv.text

        # 報到後預約是 executed 不是 booked，所以退回的那格直接回到 reserved，
        # 恆等式維持 6 = 0(used) + 6(reserved) + 0(booked)
        e = _assert_identity(db, ctx)
        assert e.used_count == 0, "作廢後已使用要退回"
        assert e.reserved_count == QUOTA_LIMIT, "退回的那格回到 reserved"
        db.refresh(pool)
        assert float(pool.consumed_total) == 0.0, "額度池也要退，否則年度池只減不加"
