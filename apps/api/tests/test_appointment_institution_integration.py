"""端到端整合測試：真的打 POST /appointments 帶 plan_id，走過
「報價 → reserve → 已到（materialize/consume）→ SessionRecord 快照」全程。

這支測試存在的理由：tests/test_institution_subsystem.py 測的是 adapter 的
方法本身（單元層級，直接呼叫 provider.xxx()）；這支測的是它們有沒有被
**正確接進真實的請求路徑**（routers/appointments.py、services/settlement.py）
——也就是 08_實作進度與系統架構現況.html §5「整合點標記」完成後，
第一支驗證「真的接上了」的測試。

情境沿用 07 §1.1 模式③：衛生局市民，單一固定價（先用固定價方案，
不測 visit_seq 分級，讓這支測試聚焦在「路徑接得對不對」而非「報價算得
對不對」——後者已經被 test_institution_subsystem.py 覆蓋）。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.case import Case
from app.models.institution import Institution
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.settlement import materialize_due_appointments

client = TestClient(app)


def _seed(db):
    admin = User(email="int_admin@test.local", password_hash=hash_password("x"), name="整合測試管理員", role="admin", user_code="A700")
    therapist = User(
        email="int_t@test.local", password_hash=hash_password("x"), name="整合測試心理師",
        role="therapist", user_code="T700", commission_rate=Decimal("0.70"),
    )
    db.add_all([admin, therapist])
    db.flush()

    inst = Institution(name="整合測試機構")
    db.add(inst)
    db.flush()

    room = Room(name="int room", floor=1, room_code="INT-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()

    case = Case(
        name="整合測試個案", therapist_id=therapist.id, funding_source="institution",
        institution_id=inst.id, status="ongoing", case_number="99INT0001",  # 已初診，consume() 才不會被擋
    )
    db.add(case)
    db.flush()

    contract = InstContract(institution_id=inst.id, name="整合測試方案合約", created_by=admin.id)
    db.add(contract)
    db.flush()

    plan = InstPlan(
        contract_id=contract.id, name="整合測試方案", quota_unit="count", default_quota_limit_numeric=3,
        compensation_mode="commission", case_receipt_required=True, case_receipt_item_name="場地費",
        claim_group_key="整合測試方案", claim_timing="monthly", created_by=admin.id,
    )
    db.add(plan)
    db.flush()
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1800, case_payable=300, label="固定價"))
    db.flush()

    from app.institution.adapter import InstitutionFundingProvider

    provider = InstitutionFundingProvider()
    enrollment = provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
    db.commit()

    token = create_access_token({"sub": str(admin.id), "role": "admin", "name": admin.name})
    return {
        "admin_id": admin.id, "therapist_id": therapist.id, "room_id": room.id, "case_id": case.id,
        "plan_id": plan.id, "enrollment_id": enrollment.enrollment_id, "token": token,
    }


class TestBookingThroughHttp:
    def test_create_appointment_with_plan_id_derives_amount_and_reserves(self, db, http_db):
        ctx = _seed(db)
        headers = {"Authorization": f"Bearer {ctx['token']}"}
        start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=1, hours=1)).isoformat()

        r = client.post(
            "/appointments",
            headers=headers,
            json={
                "case_id": ctx["case_id"], "therapist_id": ctx["therapist_id"], "room_id": ctx["room_id"],
                "session_type": "in_person", "start_time": start, "end_time": end,
                "plan_id": ctx["plan_id"],  # amount 故意不給，讓報價決定
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["amount"] == 1800.0, "amount 應該由報價的 unit_price 推導，未指定 plan_id 時才要求手動填"
        assert body["case_payable"] == 300.0
        assert body["institution_payable"] == 1500.0
        assert body["plan_id"] == ctx["plan_id"]
        assert body["plan_name"] == "整合測試方案", "plan_name 應該從存下來的 plan_quote 快照讀出，不查 inst_plans"
        assert body["funding_source"] == "institution"
        assert body["compensation_mode"] == "commission"

        row = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        assert row.reserved_count == 2, "reserve() 應該已經在同一交易內被呼叫，已預留 3→2"

    def test_blocking_quota_rejected_with_400_not_500(self, db, http_db):
        """額度用罄時應該乾淨地回 400（quote.quota.blocking），不是讓例外洩漏成 500。"""
        ctx = _seed(db)
        headers = {"Authorization": f"Bearer {ctx['token']}"}
        row = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        row.reserved_count = 0  # 模擬額度已全數用罄
        db.commit()

        start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=1, hours=1)).isoformat()
        r = client.post(
            "/appointments",
            headers=headers,
            json={
                "case_id": ctx["case_id"], "therapist_id": ctx["therapist_id"], "room_id": ctx["room_id"],
                "session_type": "in_person", "start_time": start, "end_time": end,
                "plan_id": ctx["plan_id"],
            },
        )
        assert r.status_code == 400
        assert "已用罄" in r.json()["detail"]


class TestMaterializeConsumesQuotaAndCopiesSnapshot:
    def test_past_appointment_materializes_and_consumes(self, db, http_db):
        """整個閉環：建立一筆已經「過去」的預約 → materialize_due_appointments()
        觸發 consume() → 額度 已預約(booked) 轉 已使用 → SessionRecord 帶著完整快照。
        """
        ctx = _seed(db)
        headers = {"Authorization": f"Bearer {ctx['token']}"}
        # 開始時間在 30 分鐘前、結束在 20 分鐘前——超過 SETTLEMENT_LEAD_MINUTES(20)，
        # materialize_due_appointments() 才會把它撈進來。
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        end = datetime.now(timezone.utc) - timedelta(minutes=25)
        r = client.post(
            "/appointments",
            headers=headers,
            json={
                "case_id": ctx["case_id"], "therapist_id": ctx["therapist_id"], "room_id": ctx["room_id"],
                "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
                "plan_id": ctx["plan_id"],
            },
        )
        assert r.status_code == 201, r.text
        appt_id = r.json()["id"]

        result = materialize_due_appointments(db)
        assert result["materialized"] == 1, result

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr is not None
        assert sr.plan_id == ctx["plan_id"]
        assert sr.case_payable == Decimal("300.00")
        assert sr.institution_payable == Decimal("1500.00")
        assert sr.compensation_mode == "commission"
        assert sr.plan_quote is not None and sr.plan_quote["plan_name"] == "整合測試方案"

        row = db.query(InstEnrollment).filter(InstEnrollment.id == ctx["enrollment_id"]).first()
        assert row.used_count == 1, "consume() 應該已經在 materialize 內被呼叫"
        assert row.reserved_count == 2  # 不變，reserve() 已經在建立預約時扣過了
