"""機構子系統 Layer 2 原語的補完：額度池、週期子上限、延長、核銷案作廢、
次數制候選名單。見 V2升級計畫 09 §3.3／§5（首批 5 份合約要用到的規則）。
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.funding.dto import QuoteRequest
from app.institution.adapter import InstitutionFundingProvider
from app.institution.claims import service as claims_service
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.quota_pool import InstQuotaPool
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.institution import Institution
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from psycopg2.extras import DateTimeTZRange

client = TestClient(app)
provider = InstitutionFundingProvider()


def _seed(db, quota_pool_kwargs=None, period_limit=None, period_unit=None):
    admin = User(email="l2_admin@test.local", password_hash=hash_password("x"), name="Layer2測試管理員", role="admin", user_code="A900")
    therapist = User(
        email="l2_t@test.local", password_hash=hash_password("x"), name="Layer2測試心理師",
        role="therapist", user_code="T900x", commission_rate=Decimal("0.70"),
    )
    db.add_all([admin, therapist])
    db.flush()

    inst = Institution(name="Layer2測試機構")
    db.add(inst)
    db.flush()

    room = Room(name="l2 room", floor=1, room_code="L2-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()

    contract = InstContract(institution_id=inst.id, name="Layer2測試合約", created_by=admin.id)
    db.add(contract)
    db.flush()

    pool = None
    if quota_pool_kwargs is not None:
        pool = InstQuotaPool(contract_id=contract.id, name="Layer2測試池", **quota_pool_kwargs)
        db.add(pool)
        db.flush()

    plan = InstPlan(
        contract_id=contract.id, name="Layer2測試方案", quota_unit="count", default_quota_limit_numeric=10,
        quota_pool_id=pool.id if pool else None, period_limit=period_limit, period_unit=period_unit,
        compensation_mode="commission", case_receipt_required=True, case_receipt_item_name="場地費",
        claim_group_key="Layer2測試方案", claim_timing="monthly", created_by=admin.id,
    )
    db.add(plan)
    db.flush()
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1000, case_payable=0, label="固定價"))
    db.flush()

    case = Case(
        name="Layer2測試個案", therapist_id=therapist.id, funding_source="institution",
        institution_id=inst.id, status="ongoing", case_number="99L200001",
    )
    db.add(case)
    db.flush()

    enrollment = provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
    # 用 flush() 不用 commit()：這支測試檔案的 test_cannot_void_twice 會讓
    # void endpoint 的例外處理路徑對這個共用 session 呼叫 db.rollback()——
    # 若這裡先真的 commit 過，後續的 rollback 可能破壞 fixture 的交易隔離
    # （同一顆雷，見 test_room_conflict_gist.py 的踩坑紀錄）。flush() 一樣
    # 能讓 http_db 共用同一個 session 的 HTTP 請求看到這些資料。
    db.flush()

    return {
        "admin": admin, "therapist": therapist, "room": room, "case": case, "plan": plan, "pool": pool,
        "enrollment_id": enrollment.enrollment_id,
        "admin_token": create_access_token({"sub": str(admin.id), "role": "admin", "name": admin.name}),
    }


def _book_and_checkin(db, ctx, days_offset=1):
    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
    start = datetime.now(timezone.utc) + timedelta(days=days_offset)
    end = start + timedelta(hours=1)
    r = client.post("/appointments", headers=headers, json={
        "case_id": ctx["case"].id, "room_id": ctx["room"].id, "session_type": "in_person",
        "start_time": start.isoformat(), "end_time": end.isoformat(), "plan_id": ctx["plan"].id,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestQuotaPool:
    def test_quote_blocks_when_pool_amount_exhausted(self, db):
        ctx = _seed(db, quota_pool_kwargs={"unit": "amount", "total_limit": Decimal("500")})
        req = QuoteRequest(case_id=ctx["case"].id, plan_id=ctx["plan"].id, therapist_id=ctx["therapist"].id, session_type="in_person")
        quote = provider.quote(db, req)
        assert quote.quota.blocking is not None
        assert "總額度" in quote.quota.blocking

    def test_quote_allows_when_pool_has_room(self, db):
        ctx = _seed(db, quota_pool_kwargs={"unit": "amount", "total_limit": Decimal("5000")})
        req = QuoteRequest(case_id=ctx["case"].id, plan_id=ctx["plan"].id, therapist_id=ctx["therapist"].id, session_type="in_person")
        quote = provider.quote(db, req)
        assert quote.quota.blocking is None

    def test_consume_deducts_pool_amount(self, db, http_db):
        ctx = _seed(db, quota_pool_kwargs={"unit": "amount", "total_limit": Decimal("5000")})
        appt_id = _book_and_checkin(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
        assert r.status_code == 200, r.text

        pool = db.query(InstQuotaPool).filter(InstQuotaPool.id == ctx["pool"].id).first()
        assert pool.consumed_total == Decimal("1000"), "consume() 應該已經扣掉這筆的機構請款額"

    def test_consume_deducts_pool_count(self, db, http_db):
        ctx = _seed(db, quota_pool_kwargs={"unit": "count", "total_limit": Decimal("10")})
        appt_id = _book_and_checkin(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})

        pool = db.query(InstQuotaPool).filter(InstQuotaPool.id == ctx["pool"].id).first()
        assert pool.consumed_total == Decimal("1"), "count 池應該扣 1 不是扣金額"


class TestPeriodLimit:
    def test_blocks_after_period_limit_reached(self, db, http_db):
        ctx = _seed(db, period_limit=1, period_unit="month")
        appt_date = date.today() + timedelta(days=1)
        req = QuoteRequest(case_id=ctx["case"].id, plan_id=ctx["plan"].id, therapist_id=ctx["therapist"].id, session_type="in_person", appt_date=appt_date)
        quote1 = provider.quote(db, req)
        assert quote1.quota.blocking is None, "第一次在額度內，不該被擋"

        _book_and_checkin(db, ctx, days_offset=1)
        quote2 = provider.quote(db, req)
        assert quote2.quota.blocking is not None
        assert "本週期上限" in quote2.quota.blocking


class TestExtendEnrollment:
    def test_extend_increases_reserved_and_extended(self, db, http_db):
        ctx = _seed(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        before = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        before_reserved = before.reserved_count

        r = client.post(
            f"/institution/enrollments/{ctx['enrollment_id']}/extend",
            headers=headers, json={"additional_count": 3, "note": "延長測試"},
        )
        assert r.status_code == 200, r.text

        after = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        assert after.extended_count == 3
        assert after.reserved_count == before_reserved + 3
        assert after.extension_note == "延長測試"
        assert after.extension_approved_by == ctx["admin"].id


class TestClaimCaseVoid:
    def _checked_in_with_line(self, db, ctx):
        appt_id = _book_and_checkin(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        cc = claims_service.open_claim_case(db, claim_group_key=ctx["plan"].claim_group_key, created_by=ctx["admin"].id)
        claims_service.attach_records(db, cc.id, [sr.id])
        claims_service.submit(db, cc.id)
        db.commit()
        return cc.id, sr.id

    def test_void_reverts_payment_status_and_detaches_line(self, db, http_db):
        ctx = _seed(db)
        cc_id, sr_id = self._checked_in_with_line(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        sr_before = db.query(SessionRecord).filter(SessionRecord.id == sr_id).first()
        assert sr_before.payment_status == "claiming"

        r = client.put(f"/institution/claim-cases/{cc_id}/void", headers=headers, json={"reason": "測試作廢"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "void"

        sr_after = db.query(SessionRecord).filter(SessionRecord.id == sr_id).first()
        assert sr_after.payment_status == "unpaid", "作廢後應退回未核銷，可被收進新核銷案"

        from app.institution.models.claim_line import InstClaimLine
        remaining = db.query(InstClaimLine).filter(InstClaimLine.claim_case_id == cc_id).count()
        assert remaining == 0, "紀錄應該已脫離本案"

    def test_voided_record_reappears_in_uncollected(self, db, http_db):
        ctx = _seed(db)
        cc_id, sr_id = self._checked_in_with_line(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.put(f"/institution/claim-cases/{cc_id}/void", headers=headers, json={"reason": "測試作廢"})

        rows = claims_service.list_uncollected(db, ctx["plan"].claim_group_key)
        assert sr_id in [r.id for r in rows]

    def test_cannot_void_twice(self, db, http_db):
        ctx = _seed(db)
        cc_id, _ = self._checked_in_with_line(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.put(f"/institution/claim-cases/{cc_id}/void", headers=headers, json={"reason": "第一次"})
        r = client.put(f"/institution/claim-cases/{cc_id}/void", headers=headers, json={"reason": "第二次"})
        assert r.status_code == 400


class TestPerCaseCountCandidates:
    def test_marks_ready_when_capacity_reached(self, db, http_db):
        ctx = _seed(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        for i in range(3):
            appt_id = _book_and_checkin(db, ctx, days_offset=-(i + 1))
            client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})

        candidates = claims_service.list_per_case_count_candidates(db, ctx["plan"].claim_group_key, capacity=3)
        assert len(candidates) == 1
        row = candidates[0]
        assert row["case_id"] == ctx["case"].id
        assert row["count"] == 3
        assert row["ready"] is True

    def test_not_ready_below_capacity(self, db, http_db):
        ctx = _seed(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        appt_id = _book_and_checkin(db, ctx, days_offset=-1)
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})

        candidates = claims_service.list_per_case_count_candidates(db, ctx["plan"].claim_group_key, capacity=4)
        assert candidates[0]["ready"] is False


class TestInstitutionDocGateEndpoints:
    """app/routers/ledger.py 的 /pending-docs、/confirmed-docs 只認舊路徑
    （claim_batch_id IS NOT NULL），機構子系統紀錄的 claim_batch_id 永遠是
    NULL，本來完全不會出現——這裡驗證新補的機構版本端點正確找得到它們。
    """

    def test_pending_before_submission(self, db, http_db):
        ctx = _seed(db)
        appt_id = _book_and_checkin(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})

        r = client.get(f"/institution/claim-groups/{ctx['plan'].claim_group_key}/pending-docs", headers=headers)
        assert r.status_code == 200, r.text
        appt_ids = [row["appointment_id"] for row in r.json()]
        assert appt_id in appt_ids

        r2 = client.get(f"/institution/claim-groups/{ctx['plan'].claim_group_key}/confirmed-docs", headers=headers)
        assert appt_id not in [row["appointment_id"] for row in r2.json()]

    def test_moves_to_confirmed_after_therapist_submits(self, db, http_db):
        ctx = _seed(db)
        appt_id = _book_and_checkin(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()

        r = client.put(f"/ledger/{sr.id}/confirm-doc", headers=headers)
        assert r.status_code == 200, r.text

        pending = client.get(f"/institution/claim-groups/{ctx['plan'].claim_group_key}/pending-docs", headers=headers).json()
        assert appt_id not in [row["appointment_id"] for row in pending]
        confirmed = client.get(f"/institution/claim-groups/{ctx['plan'].claim_group_key}/confirmed-docs", headers=headers).json()
        assert appt_id in [row["appointment_id"] for row in confirmed]
