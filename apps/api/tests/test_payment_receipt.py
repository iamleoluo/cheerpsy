"""報到三步驟的後兩步：收款、開立收據。見 01 §A2、08 §8。

涵蓋：純自費案（同步既有 payment_status，不破壞 /ledger 既有流程）、
機構案的個案自付額收款（機構那份 institution_payable 完全不動，走既有
核銷案容器流程）、免收案例（機構全額）、重複收款/開據擋下、收費項目
主檔（含自訂項目）、以及三步驟串起來的完整端到端情境。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from psycopg2.extras import DateTimeTZRange

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.config import settings
from app.institution.adapter import InstitutionFundingProvider
from app.institution.models.contract import InstContract
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.fee_item import FeeItem
from app.models.institution import Institution
from app.models.receipt import Receipt
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.numbering import parse_receipt_no

client = TestClient(app)


def _seed(db):
    admin = User(email="pr_admin@test.local", password_hash=hash_password("x"), name="收款測試管理員", role="admin", user_code="A500")
    therapist = User(
        email="pr_t@test.local", password_hash=hash_password("x"), name="收款測試心理師",
        role="therapist", user_code="T500", commission_rate=Decimal("0.70"),
    )
    db.add_all([admin, therapist])
    db.flush()
    room = Room(name="pr room", floor=1, room_code="PR-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()
    return {
        "admin": admin, "therapist": therapist, "room": room,
        "admin_token": create_access_token({"sub": str(admin.id), "role": "admin", "name": admin.name}),
    }


def _checked_in_self_pay_appt(db, ctx, amount=2000):
    case = Case(name="收款自費個案", therapist_id=ctx["therapist"].id, funding_source="self_pay", status="ongoing", case_number="99PR00001")
    db.add(case)
    db.flush()
    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
    start = datetime.now(timezone.utc) - timedelta(minutes=10)
    end = start + timedelta(hours=1)
    r = client.post("/appointments", headers=headers, json={
        "case_id": case.id, "therapist_id": ctx["therapist"].id, "room_id": ctx["room"].id,
        "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
        "amount": amount, "funding_source": "self_pay",
    })
    appt_id = r.json()["id"]
    r2 = client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
    assert r2.status_code == 200, r2.text
    return appt_id


def _checked_in_institution_appt(db, ctx, case_payable, institution_payable):
    inst = Institution(name="收款測試機構")
    db.add(inst)
    db.flush()
    case = Case(
        name="收款機構個案", therapist_id=ctx["therapist"].id, funding_source="institution",
        institution_id=inst.id, status="ongoing", case_number="99PR00002",
    )
    db.add(case)
    db.flush()
    contract = InstContract(institution_id=inst.id, name="收款測試合約", created_by=ctx["admin"].id)
    db.add(contract)
    db.flush()
    plan = InstPlan(
        contract_id=contract.id, name="收款測試方案", quota_unit="count", default_quota_limit_numeric=3,
        compensation_mode="commission", case_receipt_required=True, case_receipt_item_name="場地費",
        claim_group_key="收款測試方案", claim_timing="monthly", created_by=ctx["admin"].id,
    )
    db.add(plan)
    db.flush()
    unit_price = case_payable + institution_payable
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=unit_price, case_payable=case_payable, label="固定價"))
    db.flush()

    provider = InstitutionFundingProvider()
    provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=ctx["admin"].id)
    db.commit()

    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
    start = datetime.now(timezone.utc) - timedelta(minutes=10)
    end = start + timedelta(hours=1)
    r = client.post("/appointments", headers=headers, json={
        "case_id": case.id, "therapist_id": ctx["therapist"].id, "room_id": ctx["room"].id,
        "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
        "plan_id": plan.id,
    })
    assert r.status_code == 201, r.text
    appt_id = r.json()["id"]
    r2 = client.put(f"/appointments/{appt_id}/check-in", headers=headers, json={"status": "arrived"})
    assert r2.status_code == 200, r2.text
    return appt_id


class TestPaymentStepSelfPay:
    def test_payment_step_syncs_legacy_payment_status(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx, amount=2000)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        r = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["payable_amount"] == 2000.0
        assert body["copay_payment_method"] == "cash"

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr.copay_collected_at is not None
        assert sr.payment_status == "paid", "純自費案應同步既有 payment_status，讓 /ledger 頁面看到正確狀態"
        assert sr.paid_at is not None

    def test_transfer_requires_note(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "transfer"})
        assert r.status_code == 400
        assert "匯款" in r.json()["detail"]

    def test_double_payment_rejected(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r1 = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        assert r1.status_code == 200
        r2 = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        assert r2.status_code == 400
        assert "已收款過" in r2.json()["detail"]

    def test_not_checked_in_yet_rejected(self, db, http_db):
        ctx = _seed(db)
        case = Case(name="未報到個案", therapist_id=ctx["therapist"].id, funding_source="self_pay", status="ongoing", case_number="99PR00099")
        db.add(case)
        db.flush()
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        end = start + timedelta(hours=1)
        r = client.post("/appointments", headers=headers, json={
            "case_id": case.id, "therapist_id": ctx["therapist"].id, "room_id": ctx["room"].id,
            "session_type": "in_person", "start_time": start.isoformat(), "end_time": end.isoformat(),
            "amount": 2000, "funding_source": "self_pay",
        })
        appt_id = r.json()["id"]
        r2 = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        assert r2.status_code == 400
        assert "尚未報到" in r2.json()["detail"]


class TestPaymentStepInstitution:
    def test_only_case_payable_collected_institution_untouched(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_institution_appt(db, ctx, case_payable=Decimal("400"), institution_payable=Decimal("1600"))
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        r = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        assert r.status_code == 200, r.text
        assert r.json()["payable_amount"] == 400.0, "機構案只收個案自付額，不是全額"

        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr.copay_collected_at is not None
        assert sr.payment_status == "unpaid", "機構請款進度不該被這個端點動到——那是核銷案容器的事"

    def test_institution_full_coverage_no_collection_needed(self, db, http_db):
        """機構全額（case_payable=0）：免收，收款步驟應該擋下並說明原因。"""
        ctx = _seed(db)
        appt_id = _checked_in_institution_appt(db, ctx, case_payable=Decimal("0"), institution_payable=Decimal("1600"))
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        assert r.status_code == 400
        assert "免收" in r.json()["detail"]


class TestReceipt:
    def test_full_three_step_flow(self, db, http_db):
        """完整走一次：報到 → 收款 → 開立收據。"""
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx, amount=2000)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})

        fee_item = db.query(FeeItem).filter(FeeItem.name == "心理治療").first()
        r = client.post(f"/appointments/{appt_id}/receipt", headers=headers, json={"fee_item_id": fee_item.id})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["amount"] == 2000.0
        assert body["fee_item_name"] == "心理治療"
        # 收據號格式可切換（01 §C4 未定案，預設 v7），所以不寫死前綴字母，
        # 改為斷言「能被目前啟用的格式解析」——換格式時這個測試不用改。
        parsed = parse_receipt_no(body["receipt_no"])
        assert parsed is not None, body["receipt_no"]
        assert parsed["format"] == settings.RECEIPT_NUMBER_FORMAT
        assert parsed["state"] == 1  # 開立

        receipt = db.query(Receipt).filter(Receipt.id == body["id"]).first()
        assert receipt is not None
        assert receipt.status == "issued"

    def test_custom_fee_item_name(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        r = client.post(f"/appointments/{appt_id}/receipt", headers=headers, json={"fee_item_custom_name": "團體督導"})
        assert r.status_code == 201
        assert r.json()["fee_item_name"] == "團體督導"

    def test_receipt_before_payment_rejected(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.post(f"/appointments/{appt_id}/receipt", headers=headers, json={"fee_item_custom_name": "測試"})
        assert r.status_code == 400
        assert "尚未收款" in r.json()["detail"]

    def test_duplicate_receipt_rejected(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        fee_item = db.query(FeeItem).filter(FeeItem.name == "心理治療").first()
        r1 = client.post(f"/appointments/{appt_id}/receipt", headers=headers, json={"fee_item_id": fee_item.id})
        assert r1.status_code == 201
        r2 = client.post(f"/appointments/{appt_id}/receipt", headers=headers, json={"fee_item_id": fee_item.id})
        assert r2.status_code == 400
        assert "已開立過收據" in r2.json()["detail"]

    def test_missing_fee_item_rejected(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        r = client.post(f"/appointments/{appt_id}/receipt", headers=headers, json={})
        assert r.status_code == 400
        assert "收款項目" in r.json()["detail"]
