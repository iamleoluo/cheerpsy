"""Layer 3 骨架：GET /institution/contracts/{id}/panel（通用版）。
見 V2升級計畫 09 §3.1–§3.5。這支測試驗證的是「read model 的形狀正確、
會依方案欄位長出不同區塊」，不是機構規則本身（那些已經在
test_institution_layer2_primitives.py 覆蓋）。
"""

from datetime import date, datetime, timezone
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
from app.models.user import User

client = TestClient(app)
provider = InstitutionFundingProvider()


def _seed_contract_with_two_plans(db):
    admin = User(email="panel_admin@test.local", password_hash=hash_password("x"), name="面板測試管理員", role="admin", user_code="A950")
    db.add(admin)
    db.flush()

    inst = Institution(name="面板測試機構")
    db.add(inst)
    db.flush()

    contract = InstContract(institution_id=inst.id, name="面板測試合約", contact_name="王小姐", created_by=admin.id)
    db.add(contract)
    db.flush()

    pool = InstQuotaPool(contract_id=contract.id, name="面板測試池", unit="amount", total_limit=Decimal("50000"), consumed_total=Decimal("12000"))
    db.add(pool)
    db.flush()

    # 方案 A：金額池型，無個人上限
    plan_pool = InstPlan(
        contract_id=contract.id, name="池型方案", quota_pool_id=pool.id, quota_unit="amount",
        compensation_mode="commission", claim_group_key="面板測試群組", claim_grouping_mode="period",
        created_by=admin.id,
    )
    db.add(plan_pool)
    db.flush()
    db.add(InstRateRule(plan_id=plan_pool.id, sort_order=1, when_json="{}", unit_price=1800, case_payable=200, label="固定價"))

    # 方案 B：次數制核銷、有週期子上限、需要外部代號、有文件清單
    plan_count = InstPlan(
        contract_id=contract.id, name="次數制方案", quota_unit="count", default_quota_limit_numeric=6,
        period_limit=4, period_unit="month", requires_external_code=True,
        compensation_mode="commission", claim_group_key="面板測試群組2", claim_grouping_mode="per_case_count",
        claim_capacity=4, admin_checklist='["同意書"]', therapist_checklist='["簽到表"]', created_by=admin.id,
    )
    db.add(plan_count)
    db.flush()
    db.add(InstRateRule(plan_id=plan_count.id, sort_order=1, when_json="{}", unit_price=1000, case_payable=0, label="固定價"))
    db.flush()

    case = Case(name="面板測試個案", therapist_id=admin.id, funding_source="institution", institution_id=inst.id, status="ongoing", case_number="99PANEL01")
    db.add(case)
    db.flush()
    provider.enroll(db, case_id=case.id, plan_id=plan_count.id, created_by=admin.id)
    db.flush()

    return {
        "contract_id": contract.id, "plan_pool_id": plan_pool.id, "plan_count_id": plan_count.id,
        "admin_token": create_access_token({"sub": str(admin.id), "role": "admin", "name": admin.name}),
    }


class TestGenericPanel:
    def test_panel_shape_and_contract_fields(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        r = client.get(f"/institution/contracts/{ctx['contract_id']}/panel", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["module"] == "generic"
        assert body["contract"]["id"] == ctx["contract_id"]
        assert body["contract"]["institution_name"] == "面板測試機構"
        assert body["contract"]["contact_name"] == "王小姐"
        assert len(body["plans"]) == 2

    def test_pool_plan_gets_quota_pool_block(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        body = client.get(f"/institution/contracts/{ctx['contract_id']}/panel", headers=headers).json()

        pool_panel = next(p for p in body["plans"] if p["plan"]["id"] == ctx["plan_pool_id"])
        assert "quota_pool" in pool_panel["blocks"]
        assert "quota_per_case" not in pool_panel["blocks"]
        assert pool_panel["quota_pool"]["total_limit"] == 50000
        assert pool_panel["quota_pool"]["consumed_total"] == 12000
        assert pool_panel["quota_pool"]["remaining"] == 38000
        assert "claim_by_period" in pool_panel["blocks"]

    def test_count_plan_gets_all_expected_blocks(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        body = client.get(f"/institution/contracts/{ctx['contract_id']}/panel", headers=headers).json()

        count_panel = next(p for p in body["plans"] if p["plan"]["id"] == ctx["plan_count_id"])
        for expected in ["quota_per_case", "period_sublimit", "claim_by_count", "external_code", "doc_gate", "rate_table", "plan_params"]:
            assert expected in count_panel["blocks"], f"missing block: {expected}"
        assert "quota_pool" not in count_panel["blocks"]

    def test_count_plan_lists_its_enrollment(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        body = client.get(f"/institution/contracts/{ctx['contract_id']}/panel", headers=headers).json()

        count_panel = next(p for p in body["plans"] if p["plan"]["id"] == ctx["plan_count_id"])
        assert len(count_panel["enrollments"]) == 1
        assert count_panel["enrollments"][0]["case_name"] == "面板測試個案"

    def test_unregistered_contract_falls_back_to_generic(self, db, http_db):
        """尚未在 registry.py 登記專屬模組的合約，一律拿到通用版——這是
        「先做 5 個、其餘先能用」的技術前提（09 §6 第 3 步）。"""
        ctx = _seed_contract_with_two_plans(db)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        body = client.get(f"/institution/contracts/{ctx['contract_id']}/panel", headers=headers).json()
        assert body["module"] == "generic"

    def test_missing_contract_404(self, db, http_db):
        # 建一個真的 admin，不要寫死 sub='1'：那假設了「資料庫裡剛好有 id=1 的
        # 使用者」，清過庫（例如跑完假資料生成器的 --reset，會 RESTART IDENTITY）
        # 之後就會變成 401，而錯誤訊息完全看不出是環境問題而不是路由問題。
        admin = User(email="panel_404@test.local", password_hash=hash_password("x"),
                     name="面板 404 測試", role="admin", user_code="A951")
        db.add(admin)
        db.flush()
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'role': 'admin', 'name': admin.name})}"}
        r = client.get("/institution/contracts/999999/panel", headers=headers)
        assert r.status_code == 404


class TestContractListAggregates:
    """清單頁每列的兩個數字 —— 09 §3.7。

    行政原本必須一份一份點進合約專頁才知道裡面什麼狀況，因為清單只有合約名
    與面板標記。這幾個欄位讓一張表就看得完，且刻意由後端**一次聚合**算出：
    11 份合約逐份查就是 33 次查詢，而這頁是機構作業的入口（11 §4.1）。
    """

    def _row(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        r = client.get(
            "/institution/contracts?include_inactive=true",
            headers={"Authorization": f"Bearer {ctx['admin_token']}"},
        )
        assert r.status_code == 200, r.text
        return next(x for x in r.json() if x["id"] == ctx["contract_id"])

    def test_plan_and_case_counts(self, db, http_db):
        row = self._row(db, http_db)
        assert row["plan_count"] == 2
        assert row["active_case_count"] == 1

    def test_pool_wins_over_per_case(self, db, http_db):
        """合約同時有池子時以池子為準——那才是行政要盯的天花板。"""
        row = self._row(db, http_db)
        assert row["quota_scope"] == "pool"
        assert row["quota_unit"] == "amount"
        assert row["quota_limit"] == 50000.0
        assert row["quota_used"] == 12000.0


class TestExternalCaseCode:
    """個案代號事後登錄 —— 07 §1.6 / 09 §3.5 的 external_code 區塊。

    代號是機構端配發的，通常在個案已經開始接受服務之後才拿到。原本只有
    POST /enrollments 建立當下能填，之後沒有任何入口——而核銷收納會用這個
    欄位擋下（claims/service.py），所以掛方案時沒填的個案等於**永遠無法核銷**。
    """

    def _enrollment_id(self, db, ctx):
        from app.institution.models.enrollment import InstEnrollment

        return db.query(InstEnrollment).filter(
            InstEnrollment.plan_id == ctx["plan_count_id"]
        ).first().id

    def test_can_set_and_clear(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        eid = self._enrollment_id(db, ctx)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        r = client.put(f"/institution/enrollments/{eid}/external-code",
                       json={"external_case_code": "HB-2026-0031"}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["external_case_code"] == "HB-2026-0031"

        # 清空：留白等於沒有代號，不是留下空字串（收納那邊用 strip() 判斷）
        r = client.put(f"/institution/enrollments/{eid}/external-code",
                       json={"external_case_code": "   "}, headers=headers)
        assert r.status_code == 200
        assert r.json()["external_case_code"] is None

    def test_unknown_enrollment_404(self, db, http_db):
        ctx = _seed_contract_with_two_plans(db)
        r = client.put("/institution/enrollments/99999999/external-code",
                       json={"external_case_code": "X"},
                       headers={"Authorization": f"Bearer {ctx['admin_token']}"})
        assert r.status_code == 404


class TestReturnedDocsVisibility:
    """退回補件要讓心理師看得見 —— 10 §6。

    退回時只清掉兩個閘門，原因寫進稽核與通知、**沒有存在紀錄上**。所以被退回
    的那筆在心理師的「文件確認」頁看起來跟「從沒交過」一模一樣：

        「原本只有 admin-unverify：清一側、沒原因、不通知，
          心理師根本不知道自己被退件」

    pending-docs 現在把最後一次退回的時間與原因帶出來。
    """

    def test_returned_record_carries_reason(self, db, http_db):
        from app.institution.claims import service as claims_service
        from app.institution.models.enrollment import InstEnrollment  # noqa: F401
        from app.institution.routers.admin import list_all_institution_pending_docs
        from app.models.session_record import SessionRecord
        from app.models.user import User as U

        ctx = _seed_contract_with_two_plans(db)
        admin = db.query(U).filter(U.role == "admin").first()

        sr = SessionRecord(
            session_date=date(2026, 5, 4), therapist_id=admin.id,
            amount=Decimal("1000"), session_type="in_person",
            funding_source="institution", payment_status="unpaid",
            plan_id=ctx["plan_count_id"],
            therapist_doc_submitted_at=datetime.now(timezone.utc),
        )
        db.add(sr)
        db.flush()

        claims_service.return_for_correction(db, sr.id, "簽到表缺個案簽名", admin.id)
        db.flush()

        row = next(
            r for r in list_all_institution_pending_docs(user=admin, db=db) if r["id"] == sr.id
        )
        # 退回會把它打回「待提交」，所以它會出現在 pending 裡——重點是要看得出原因
        assert row["returned_reason"] == "簽到表缺個案簽名"
        assert row["returned_at"] is not None

    def test_never_submitted_has_no_reason(self, db, http_db):
        from app.institution.routers.admin import list_all_institution_pending_docs
        from app.models.session_record import SessionRecord
        from app.models.user import User as U

        ctx = _seed_contract_with_two_plans(db)
        admin = db.query(U).filter(U.role == "admin").first()
        sr = SessionRecord(
            session_date=date(2026, 5, 5), therapist_id=admin.id,
            amount=Decimal("1000"), session_type="in_person",
            funding_source="institution", payment_status="unpaid",
            plan_id=ctx["plan_count_id"], therapist_doc_submitted_at=None,
        )
        db.add(sr)
        db.flush()

        row = next(
            r for r in list_all_institution_pending_docs(user=admin, db=db) if r["id"] == sr.id
        )
        assert row["returned_reason"] is None
