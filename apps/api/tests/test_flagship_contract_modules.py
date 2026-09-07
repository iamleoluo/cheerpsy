"""首批 5 份專屬合約模組（09 §3.3）。合約名稱要跟
app/institution/contracts/registry.py 的 BY_CONTRACT_NAME 完全比對才會
分派到專屬模組，不對到就退回通用版——這裡驗證的正是「對到名稱→拿到
對的 module 標籤與導引欄位」，以及「名稱沒對到→安全退化」。
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.institution.adapter import InstitutionFundingProvider
from app.institution.models.contract import InstContract
from app.institution.models.plan import InstPlan
from app.institution.models.quota_pool import InstQuotaPool
from app.institution.models.rate_rule import InstRateRule
from app.main import app
from app.models.case import Case
from app.models.institution import Institution
from app.models.session_record import SessionRecord
from app.models.user import User

client = TestClient(app)
provider = InstitutionFundingProvider()


def _admin(db, email="flagship_admin@test.local", code="A970"):
    admin = User(email=email, password_hash=hash_password("x"), name="旗艦模組測試管理員", role="admin", user_code=code)
    db.add(admin)
    db.flush()
    return admin


def _token(user):
    return create_access_token({"sub": str(user.id), "role": "admin", "name": user.name})


class TestHealthBureauModule:
    def test_dispatches_and_flags_last_visit(self, db, http_db):
        admin = _admin(db)
        inst = Institution(name="臺南市政府衛生局_test")
        db.add(inst)
        db.flush()
        contract = InstContract(institution_id=inst.id, name="衛生局市民", created_by=admin.id)
        db.add(contract)
        db.flush()
        plan = InstPlan(
            contract_id=contract.id, name="衛生局市民", quota_unit="count", default_quota_limit_numeric=2,
            compensation_mode="commission", claim_group_key="衛生局市民_test", created_by=admin.id,
        )
        db.add(plan)
        db.flush()
        db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=0, label="固定價"))
        case = Case(name="衛生局測試個案", therapist_id=admin.id, funding_source="institution", institution_id=inst.id, status="ongoing", case_number="99HB0001")
        db.add(case)
        db.flush()
        e = provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)

        # 手動把 reserved 降到 1（模擬只剩最後一次）
        from app.institution.models.enrollment import InstEnrollment
        enrollment = db.query(InstEnrollment).filter(InstEnrollment.id == e.enrollment_id).first()
        enrollment.reserved_count = 1
        db.flush()

        headers = {"Authorization": f"Bearer {_token(admin)}"}
        r = client.get(f"/institution/contracts/{contract.id}/panel", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["module"] == "health_bureau"
        assert any("最後一次" in a for a in body["guidance"]["alerts"])


class TestMilitaryModule:
    def test_dispatches_and_warns_on_low_pool(self, db, http_db):
        admin = _admin(db, email="flagship_mil@test.local", code="A971")
        inst = Institution(name="國防部政治作戰局_test")
        db.add(inst)
        db.flush()
        contract = InstContract(institution_id=inst.id, name="國軍心理照護方案", created_by=admin.id)
        db.add(contract)
        db.flush()
        pool = InstQuotaPool(contract_id=contract.id, name="國軍年度總額度_test", unit="amount", total_limit=Decimal("100000"), consumed_total=Decimal("90000"))
        db.add(pool)
        db.flush()
        plan = InstPlan(
            contract_id=contract.id, name="國軍-個別_test", quota_pool_id=pool.id, quota_unit="count",
            default_quota_limit_numeric=6, requires_external_code=True, compensation_mode="commission",
            claim_group_key="國軍_test", created_by=admin.id,
        )
        db.add(plan)
        db.flush()
        db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=400, label="固定價"))
        db.flush()

        headers = {"Authorization": f"Bearer {_token(admin)}"}
        r = client.get(f"/institution/contracts/{contract.id}/panel", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["module"] == "military"
        assert body["guidance"]["headline_pool"]["remaining"] == 10000
        assert any("即將用罄" in a for a in body["guidance"]["alerts"])


class TestCountBasedClaimModule:
    def test_dispatches_and_surfaces_ready_cases(self, db, http_db):
        admin = _admin(db, email="flagship_hr@test.local", code="A972")
        inst = Institution(name="台南市政府人事處_test")
        db.add(inst)
        db.flush()
        contract = InstContract(institution_id=inst.id, name="市政府人事處", created_by=admin.id)
        db.add(contract)
        db.flush()
        plan = InstPlan(
            contract_id=contract.id, name="市政府人事處_test", quota_unit="count", default_quota_limit_numeric=4,
            requires_external_code=True, compensation_mode="commission",
            claim_group_key="人事處測試", claim_grouping_mode="per_case_count", claim_capacity=2,
            created_by=admin.id,
        )
        db.add(plan)
        db.flush()
        db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=0, label="固定價"))
        therapist = User(email="flagship_hr_t@test.local", password_hash=hash_password("x"), name="人事處測試心理師", role="therapist", user_code="T972", commission_rate=Decimal("0.70"))
        db.add(therapist)
        db.flush()
        case = Case(name="人事處測試個案", therapist_id=therapist.id, funding_source="institution", institution_id=inst.id, status="ongoing", case_number="99HR0001")
        db.add(case)
        db.flush()
        provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
        db.flush()

        from app.models.room import Room
        room = Room(name="hr room", floor=1, room_code="HR-1A", use_type="general", size="normal")
        db.add(room)
        db.flush()
        headers = {"Authorization": f"Bearer {_token(admin)}"}
        from datetime import datetime, timedelta, timezone
        for i in range(2):
            start = datetime.now(timezone.utc) + timedelta(days=-(i + 1))
            end = start + timedelta(hours=1)
            r = client.post("/appointments", headers=headers, json={
                "case_id": case.id, "room_id": room.id, "session_type": "in_person",
                "start_time": start.isoformat(), "end_time": end.isoformat(), "plan_id": plan.id,
            })
            assert r.status_code == 201, r.text
            client.put(f"/appointments/{r.json()['id']}/check-in", headers=headers, json={"status": "arrived"})

        r = client.get(f"/institution/contracts/{contract.id}/panel", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["module"] == "count_based_claim"
        assert len(body["guidance"]["ready_to_claim"]) == 1
        assert body["guidance"]["ready_to_claim"][0]["case_id"] == case.id


class TestKickbackModule:
    def test_dispatches_and_summarizes_by_therapist(self, db, http_db):
        admin = _admin(db, email="flagship_kb@test.local", code="A973")
        inst = Institution(name="教育部_教師諮商輔導支持中心_test")
        db.add(inst)
        db.flush()
        contract = InstContract(institution_id=inst.id, name="教支中心", created_by=admin.id)
        db.add(contract)
        db.flush()
        plan = InstPlan(
            contract_id=contract.id, name="教支中心_test", quota_unit="count", default_quota_limit_numeric=6,
            requires_external_code=True, compensation_mode="kickback", claim_group_key="教支中心測試",
            created_by=admin.id,
        )
        db.add(plan)
        db.flush()
        db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=2000, case_payable=0, label="固定價"))
        therapist = User(email="flagship_kb_t@test.local", password_hash=hash_password("x"), name="教支測試心理師", role="therapist", user_code="T973", commission_rate=Decimal("0.70"))
        db.add(therapist)
        db.flush()
        case = Case(name="教支測試個案", therapist_id=therapist.id, funding_source="institution", institution_id=inst.id, status="ongoing", case_number="99KB0001")
        db.add(case)
        db.flush()
        provider.enroll(db, case_id=case.id, plan_id=plan.id, created_by=admin.id)
        db.flush()

        from app.models.room import Room
        from datetime import datetime, timedelta, timezone
        room = Room(name="kb room", floor=1, room_code="KB-1A", use_type="general", size="normal")
        db.add(room)
        db.flush()
        headers = {"Authorization": f"Bearer {_token(admin)}"}
        start = datetime.now(timezone.utc) + timedelta(days=-1)
        end = start + timedelta(hours=1)
        r = client.post("/appointments", headers=headers, json={
            "case_id": case.id, "room_id": room.id, "session_type": "in_person",
            "start_time": start.isoformat(), "end_time": end.isoformat(), "plan_id": plan.id,
        })
        assert r.status_code == 201, r.text
        client.put(f"/appointments/{r.json()['id']}/check-in", headers=headers, json={"status": "arrived"})

        r = client.get(f"/institution/contracts/{contract.id}/panel", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["module"] == "kickback"
        summary = body["guidance"]["kickback_summary"]
        assert len(summary) == 1
        assert summary[0]["therapist_name"] == "教支測試心理師"
        assert summary[0]["session_count"] == 1
        assert summary[0]["total_collected"] == 2000.0


class TestVenueRentalModule:
    def test_dispatches_and_drops_quota_block(self, db, http_db):
        admin = _admin(db, email="flagship_vr@test.local", code="A974")
        inst = Institution(name="鉅微管理顧問股份有限公司_test")
        db.add(inst)
        db.flush()
        contract = InstContract(institution_id=inst.id, name="鉅微借場地", created_by=admin.id)
        db.add(contract)
        db.flush()
        plan = InstPlan(
            contract_id=contract.id, name="鉅微/借場地_test", quota_unit="count", counts_toward_quota=False,
            compensation_mode="none", claim_group_key="鉅微測試", created_by=admin.id,
        )
        db.add(plan)
        db.flush()
        db.add(InstRateRule(plan_id=plan.id, sort_order=1, when_json="{}", unit_price=500, case_payable=0, label="每小時"))
        db.flush()

        headers = {"Authorization": f"Bearer {_token(admin)}"}
        r = client.get(f"/institution/contracts/{contract.id}/panel", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["module"] == "venue_rental"
        assert "quota_unlimited" not in body["plans"][0]["blocks"]
        assert "venue_summary" in body["guidance"]


class TestFallback:
    def test_unmatched_name_falls_back_to_generic(self, db, http_db):
        admin = _admin(db, email="flagship_fb@test.local", code="A975")
        inst = Institution(name="隨便一個機構_test")
        db.add(inst)
        db.flush()
        contract = InstContract(institution_id=inst.id, name="這個名字沒對到任何模組", created_by=admin.id)
        db.add(contract)
        db.flush()

        headers = {"Authorization": f"Bearer {_token(admin)}"}
        r = client.get(f"/institution/contracts/{contract.id}/panel", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["module"] == "generic"
