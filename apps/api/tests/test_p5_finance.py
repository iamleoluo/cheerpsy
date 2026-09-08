"""P5 財務功能：收據作廢/重印、核銷退回補件、期間缺口警告、
個案代號擋下、登記時數自動換算。

這批同樣是「文件寫了但沒建」的功能（v7 核銷案、02 §1.2、07 §8.3）。
receipts 的 status/void_reason/voided_at/voided_by 四個欄位更是從建表以來
沒有任何程式碼寫過。
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.institution.adapter import InstitutionFundingProvider
from app.institution.claims import service as claims_service
from app.institution.models.claim_case import InstClaimCase
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.case import Case
from app.models.fee_item import FeeItem
from app.models.institution import Institution
from app.models.notification import Notification
from app.models.receipt import Receipt
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.numbering import parse_receipt_no

client = TestClient(app)
provider = InstitutionFundingProvider()


def _seed(db, requires_code=False, registered_rule=None):
    admin = User(email="p5_admin@test.local", password_hash=hash_password("x"),
                 name="P5測試管理員", role="admin", user_code="A930")
    therapist = User(email="p5_t@test.local", password_hash=hash_password("x"),
                     name="P5測試心理師", role="therapist", user_code="T930",
                     commission_rate=Decimal("0.70"))
    db.add_all([admin, therapist])
    db.flush()
    inst = Institution(name="P5測試機構")
    db.add(inst)
    db.flush()
    room = Room(name="p5 room", floor=1, room_code="P5-1A", use_type="general", size="normal")
    db.add(room)
    db.flush()
    case = Case(name="P5測試個案", therapist_id=therapist.id, funding_source="institution",
                institution_id=inst.id, status="ongoing", case_number="99P500001")
    db.add(case)
    db.flush()
    contract = InstContract(institution_id=inst.id, name="P5測試合約", created_by=admin.id)
    db.add(contract)
    db.flush()
    plan = InstPlan(
        contract_id=contract.id, name="P5測試方案", quota_unit="count",
        default_quota_limit_numeric=10, compensation_mode="commission",
        claim_group_key="P5測試群組", requires_external_code=requires_code,
        registered_hours_rule=registered_rule, created_by=admin.id,
    )
    db.add(plan)
    db.flush()
    db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=200, label="固定價"))
    db.flush()
    provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
    db.commit()
    return {
        "admin": admin, "therapist": therapist, "case": case, "plan": plan, "room": room,
        "h": {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'role': 'admin', 'name': admin.name})}"},
    }


def _checked_in(ctx, db, hours_ago=2, minutes=60):
    start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    r = client.post("/appointments", headers=ctx["h"], json={
        "case_id": ctx["case"].id, "room_id": ctx["room"].id, "session_type": "in_person",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=minutes)).isoformat(),
        "plan_id": ctx["plan"].id,
    })
    assert r.status_code == 201, r.text
    appt_id = r.json()["id"]
    r2 = client.put(f"/appointments/{appt_id}/check-in", headers=ctx["h"], json={"status": "arrived"})
    assert r2.status_code == 200, r2.text
    return appt_id


class TestReceiptVoidAndReprint:
    def _issued(self, ctx, db):
        appt_id = _checked_in(ctx, db)
        client.post(f"/appointments/{appt_id}/payment-step", headers=ctx["h"], json={"payment_method": "cash"})
        item = db.query(FeeItem).first()
        r = client.post(f"/appointments/{appt_id}/receipt", headers=ctx["h"],
                        json={"fee_item_id": item.id} if item else {"fee_item_custom_name": "心理治療"})
        assert r.status_code == 201, r.text
        return appt_id, r.json()["id"], r.json()["receipt_no"]

    def test_void_marks_status_and_renumbers_to_dash3(self, db, http_db):
        ctx = _seed(db)
        appt_id, rid, no = self._issued(ctx, db)
        assert parse_receipt_no(no)["state"] == 1

        r = client.put(f"/appointments/receipts/{rid}/void", headers=ctx["h"],
                       json={"reason": "金額打錯", "reissue": False})
        assert r.status_code == 200, r.text
        rows = r.json()
        voided = next(x for x in rows if x["id"] == rid)
        assert voided["status"] == "voided"
        assert voided["void_reason"] == "金額打錯"
        assert parse_receipt_no(voided["receipt_no"])["state"] == 3

    def test_void_with_reissue_creates_new_valid_receipt(self, db, http_db):
        ctx = _seed(db)
        appt_id, rid, no = self._issued(ctx, db)
        rows = client.put(f"/appointments/receipts/{rid}/void", headers=ctx["h"],
                          json={"reason": "開錯抬頭", "reissue": True}).json()
        assert len(rows) == 2
        issued = [x for x in rows if x["status"] == "issued"]
        assert len(issued) == 1
        assert parse_receipt_no(issued[0]["receipt_no"])["state"] == 1
        assert issued[0]["receipt_no"] != no

    def test_void_requires_reason(self, db, http_db):
        ctx = _seed(db)
        _, rid, _ = self._issued(ctx, db)
        r = client.put(f"/appointments/receipts/{rid}/void", headers=ctx["h"], json={"reason": "  "})
        assert r.status_code == 400

    def test_reprint_shares_base_and_keeps_original_valid(self, db, http_db):
        ctx = _seed(db)
        appt_id, rid, no = self._issued(ctx, db)
        r = client.post(f"/appointments/receipts/{rid}/reprint", headers=ctx["h"])
        assert r.status_code == 201, r.text
        copy = r.json()
        assert parse_receipt_no(copy["receipt_no"])["state"] == 2
        assert copy["receipt_no"].rsplit("-", 1)[0] == no.rsplit("-", 1)[0], "重印要沿用同一個 base"

        rows = client.get(f"/appointments/{appt_id}/receipts", headers=ctx["h"]).json()
        assert {x["status"] for x in rows} == {"issued"}, "重印不影響原件效力"

    def test_cannot_reprint_a_voided_receipt(self, db, http_db):
        ctx = _seed(db)
        _, rid, _ = self._issued(ctx, db)
        client.put(f"/appointments/receipts/{rid}/void", headers=ctx["h"],
                   json={"reason": "作廢", "reissue": False})
        r = client.post(f"/appointments/receipts/{rid}/reprint", headers=ctx["h"])
        assert r.status_code == 400


class TestReturnForCorrection:
    def test_clears_both_gates_and_notifies_therapist(self, db, http_db):
        """v7 明訂要同時清掉心理師確認與行政核對，並通知心理師。"""
        ctx = _seed(db)
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        sr.therapist_doc_submitted_at = datetime.now(timezone.utc)
        sr.therapist_doc_submitted_by = ctx["therapist"].id
        sr.admin_verified_at = datetime.now(timezone.utc)
        sr.admin_verified_by = ctx["admin"].id
        db.commit()

        r = client.put(f"/institution/records/{sr.id}/return-for-correction", headers=ctx["h"],
                       json={"reason": "出席單缺個案簽名"})
        assert r.status_code == 200, r.text

        db.expire_all()
        sr = db.query(SessionRecord).filter(SessionRecord.id == sr.id).first()
        assert sr.therapist_doc_submitted_at is None, "心理師確認要被清掉"
        assert sr.admin_verified_at is None, "行政核對也要被清掉"

        n = db.query(Notification).filter(Notification.user_id == ctx["therapist"].id).first()
        assert n is not None, "要通知心理師，否則他不會知道自己被退件"
        assert "補件" in n.title

    def test_requires_reason(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        r = client.put(f"/institution/records/{sr.id}/return-for-correction", headers=ctx["h"],
                       json={"reason": ""})
        assert r.status_code == 400

    def test_rejected_once_claimed(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        sr.payment_status = "claimed"
        db.commit()
        r = client.put(f"/institution/records/{sr.id}/return-for-correction", headers=ctx["h"],
                       json={"reason": "測試"})
        assert r.status_code == 400
        assert "已入帳" in r.json()["detail"]


class TestPeriodCoverage:
    def test_detects_gap_and_suggests_next_start(self, db, http_db):
        ctx = _seed(db)
        claims_service.open_claim_case(
            db, "P5測試群組", period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
            created_by=ctx["admin"].id)
        db.commit()

        r = client.get("/institution/claim-groups/P5測試群組/period-check", headers=ctx["h"],
                       params={"period_start": "2026-03-01", "period_end": "2026-03-31"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["suggested_start"] == "2026-02-01"
        gaps = [w for w in body["warnings"] if w["kind"] == "gap"]
        assert gaps and gaps[0]["days"] == 28, gaps

    def test_detects_overlap(self, db, http_db):
        ctx = _seed(db)
        claims_service.open_claim_case(
            db, "P5測試群組", period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
            created_by=ctx["admin"].id)
        db.commit()
        r = client.get("/institution/claim-groups/P5測試群組/period-check", headers=ctx["h"],
                       params={"period_start": "2026-04-20", "period_end": "2026-05-20"})
        overlaps = [w for w in r.json()["warnings"] if w["kind"] == "overlap"]
        assert overlaps and overlaps[0]["days"] == 11, overlaps

    def test_warnings_never_block(self, db, http_db):
        """v7 定案：缺口/重疊一律警告不阻擋——行政比系統清楚為什麼要跳過。"""
        ctx = _seed(db)
        claims_service.open_claim_case(
            db, "P5測試群組", period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
            created_by=ctx["admin"].id)
        db.commit()
        r = client.post("/institution/claim-cases", headers=ctx["h"], json={
            "claim_group_key": "P5測試群組",
            "period_start": "2026-06-15", "period_end": "2026-07-15",
        })
        assert r.status_code == 201, r.text
        assert any(w["kind"] == "overlap" for w in r.json()["warnings"])


class TestExternalCodeEnforcement:
    def test_blocks_attach_when_code_missing(self, db, http_db):
        """07 §8.3：方案要求個案代號的，缺代號送出去機構會退件。"""
        ctx = _seed(db, requires_code=True)
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        cc = claims_service.open_claim_case(db, "P5測試群組", created_by=ctx["admin"].id)
        db.commit()

        r = client.post(f"/institution/claim-cases/{cc.id}/records", headers=ctx["h"],
                        json={"session_record_ids": [sr.id]})
        assert r.status_code == 400, r.text
        assert "個案代號" in r.json()["detail"]

    def test_passes_once_code_filled(self, db, http_db):
        ctx = _seed(db, requires_code=True)
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        e = db.query(InstEnrollment).filter(InstEnrollment.case_id == ctx["case"].id).first()
        e.external_case_code = "TN-2026-0031"
        cc = claims_service.open_claim_case(db, "P5測試群組", created_by=ctx["admin"].id)
        db.commit()
        r = client.post(f"/institution/claim-cases/{cc.id}/records", headers=ctx["h"],
                        json={"session_record_ids": [sr.id]})
        assert r.status_code == 200, r.text
        assert r.json()["attached"] == 1

    def test_admin_can_override(self, db, http_db):
        ctx = _seed(db, requires_code=True)
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        cc = claims_service.open_claim_case(db, "P5測試群組", created_by=ctx["admin"].id)
        db.commit()
        r = client.post(f"/institution/claim-cases/{cc.id}/records", headers=ctx["h"],
                        json={"session_record_ids": [sr.id], "enforce_external_code": False})
        assert r.status_code == 200, r.text


class TestRegisteredHours:
    RULE = '{"multiplier": 2, "registered_unit_price": 800}'

    def test_auto_converts_hours_and_amount(self, db, http_db):
        """台南地院：實際 1 小時 $1600 → 登記 2 小時 @$800，申請金額仍是 $1600。"""
        ctx = _seed(db, registered_rule=self.RULE)
        appt_id = _checked_in(ctx, db, minutes=60)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        cc = claims_service.open_claim_case(db, "P5測試群組", created_by=ctx["admin"].id)
        db.commit()

        lines = claims_service.attach_records(db, cc.id, [sr.id])
        db.commit()
        line = lines[0]
        assert line.actual_hours == Decimal("1.00")
        assert line.registered_hours == Decimal("2.00")
        assert line.registered_unit_price == Decimal("800")
        assert line.claimed_amount == Decimal("1600")

    def test_scales_with_actual_duration(self, db, http_db):
        ctx = _seed(db, registered_rule=self.RULE)
        appt_id = _checked_in(ctx, db, minutes=90)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        cc = claims_service.open_claim_case(db, "P5測試群組", created_by=ctx["admin"].id)
        db.commit()
        line = claims_service.attach_records(db, cc.id, [sr.id])[0]
        assert line.actual_hours == Decimal("1.50")
        assert line.registered_hours == Decimal("3.00")
        assert line.claimed_amount == Decimal("2400")

    def test_free_text_rule_is_ignored_not_crashing(self, db, http_db):
        """舊的自由文字備忘不能讓收納壞掉——看不懂就當沒有規則。"""
        ctx = _seed(db, registered_rule="實際1小時$1600 -> 登記2小時，每小時$800")
        appt_id = _checked_in(ctx, db)
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        cc = claims_service.open_claim_case(db, "P5測試群組", created_by=ctx["admin"].id)
        db.commit()
        line = claims_service.attach_records(db, cc.id, [sr.id])[0]
        assert line.registered_hours is None
        assert line.claimed_amount == Decimal("1400.00"), "沒有規則就用原本的機構應付額"
