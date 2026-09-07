"""機構合約子系統的端到端回歸測試。

覆蓋 V2升級計畫 07_機構合約子系統架構.html 裡實際定案的行為，尤其是
2026/09/07 討論中修正過的兩處：
    - 額度「是否已滿」的判斷要看 reserved，不能拿 used+reserved+booked
      跟 total 比較（那是恆等式，永遠成立，測不出東西）——這支測試檔案
      本身就是在那次修正時寫的，用來鎖住這個回歸。
    - 核銷案容器可以裝不滿就送出；收入認列月份不受入帳月份影響。

情境沿用 07 §1.1 模式③ 的真實案例：衛生局市民（第1次核銷$1600/個案免付，
第2次核銷$1400/個案自付$200，個人額度2次）。
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from psycopg2.extras import DateTimeTZRange

from app.auth.password import hash_password
from app.funding.dto import QuoteRequest
from app.institution.adapter import InstitutionFundingProvider
from app.institution.claims import service as claims_service
from app.institution.models.contract import InstContract
from app.institution.models.enrollment import InstEnrollment
from app.institution.models.plan import InstPlan
from app.institution.models.rate_rule import InstRateRule
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.institution import Institution
from app.models.room import Room
from app.models.session_record import SessionRecord
from app.models.user import User

provider = InstitutionFundingProvider()


@pytest.fixture()
def hygiene_plan(db):
    """衛生局市民方案：個人額度2次，第1次$1600(自付0)、第2次$1400(自付200)。"""
    admin = User(email="t_admin@test.local", password_hash=hash_password("x"), name="測試管理員", role="admin", user_code="A800")
    therapist = User(
        email="t_therapist@test.local", password_hash=hash_password("x"), name="測試心理師",
        role="therapist", user_code="T800", commission_rate=Decimal("0.70"),
    )
    db.add_all([admin, therapist])
    db.flush()

    inst = Institution(name="臺南市政府衛生局_test", code="TST01")
    db.add(inst)
    db.flush()

    room = Room(name="test room", floor=1, room_code="TST-1A", use_type="general", size="normal")
    db.add(room)

    contract = InstContract(institution_id=inst.id, name="衛生局市民_test", created_by=admin.id)
    db.add(contract)
    db.flush()

    plan = InstPlan(
        contract_id=contract.id,
        name="衛生局市民_test",
        quota_unit="count",
        default_quota_limit_numeric=2,
        compensation_mode="commission",
        case_receipt_required=True,
        case_receipt_item_name="場地費",
        claim_group_key="衛生局市民_test",
        claim_timing="monthly",
        claim_deadline_day=10,
        admin_checklist=json.dumps(["同意書(第一次)", "簽到表"], ensure_ascii=False),
        therapist_checklist=json.dumps(["簽到表"], ensure_ascii=False),
        created_by=admin.id,
    )
    db.add(plan)
    db.flush()
    db.add_all(
        [
            InstRateRule(plan_id=plan.id, sort_order=1, when_json='{"visit_seq": 1}', unit_price=1600, case_payable=0, label="第一次"),
            InstRateRule(plan_id=plan.id, sort_order=2, when_json='{"visit_seq": 2}', unit_price=1400, case_payable=200, label="第二次"),
        ]
    )
    db.flush()
    return {"admin": admin, "therapist": therapist, "institution": inst, "room": room, "contract": contract, "plan": plan}


@pytest.fixture()
def case_with_visit_history(db, hygiene_plan):
    """有正式病歷號的個案（已完成初診）。"""
    c = Case(
        name="測試個案", therapist_id=hygiene_plan["therapist"].id, funding_source="institution",
        institution_id=hygiene_plan["institution"].id, status="ongoing", case_number="99TEST001",
    )
    db.add(c)
    db.flush()
    return c


def _make_appointment(db, hygiene_plan, case, quote, start_offset_hours=24):
    start = datetime.now(timezone.utc) + timedelta(hours=start_offset_hours)
    end = start + timedelta(hours=1)
    appt = Appointment(
        appointment_number=f"R-TEST-{start_offset_hours}",
        case_id=case.id,
        therapist_id=hygiene_plan["therapist"].id,
        room_id=hygiene_plan["room"].id,
        session_type="in_person",
        time_range=DateTimeTZRange(start, end),
        amount=quote.pricing.unit_price,
        status="booked",
        funding_source="institution",
        plan_id=hygiene_plan["plan"].id,
        case_payable=quote.pricing.case_payable,
        institution_payable=quote.pricing.institution_payable,
        compensation_mode=quote.compensation.mode,
        commissionable_base=quote.compensation.commissionable_base,
        plan_quote=json.loads(quote.model_dump_json()),
        created_by=hygiene_plan["admin"].id,
    )
    db.add(appt)
    db.flush()
    return appt


class TestEnrollAndQuota:
    def test_enroll_reserves_full_quota(self, db, hygiene_plan, case_with_visit_history):
        e = provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        assert e.reserved == 2
        assert e.used == 0

    def test_duplicate_enroll_rejected(self, db, hygiene_plan, case_with_visit_history):
        provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        with pytest.raises(ValueError, match="已加入過"):
            provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)

    def test_list_eligible_plans_not_disabled_when_reserved_available(self, db, hygiene_plan, case_with_visit_history):
        """回歸測試：reserved=2（剛加入方案）時，方案必須是可選的，不能顯示已用罄。
        這是 2026/09/07 修正的 bug——舊邏輯拿 used+reserved+booked 跟 total 比較，
        因為那是恆等式，永遠回傳「已滿」。"""
        provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        opts = provider.list_eligible_plans(db, case_with_visit_history.id, date.today())
        assert len(opts) == 1
        assert opts[0].disabled is False
        assert opts[0].is_last is False


class TestQuotePricing:
    def test_visit_seq_1_pricing(self, db, hygiene_plan, case_with_visit_history):
        provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        q = provider.quote(
            db,
            QuoteRequest(
                case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id,
                therapist_id=hygiene_plan["therapist"].id, session_type="in_person", visit_seq=1,
            ),
        )
        assert q.pricing.unit_price == Decimal("1600")
        assert q.pricing.case_payable == Decimal("0")
        assert q.pricing.institution_payable == Decimal("1600")
        assert q.quota.is_last is False
        assert q.checklists.admin == ["同意書(第一次)", "簽到表"]

    def test_visit_seq_2_is_last(self, db, hygiene_plan, case_with_visit_history):
        e = provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        # 先消耗一次額度，模擬已經做過第一次
        row = db.query(InstEnrollment).filter(InstEnrollment.id == e.enrollment_id).first()
        row.reserved_count -= 1
        row.used_count += 1
        db.flush()

        q = provider.quote(
            db,
            QuoteRequest(
                case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id,
                therapist_id=hygiene_plan["therapist"].id, session_type="in_person", visit_seq=2,
            ),
        )
        assert q.pricing.unit_price == Decimal("1400")
        assert q.pricing.case_payable == Decimal("200")
        assert q.quota.is_last is True


class TestReserveConsumeRelease:
    def test_full_lifecycle(self, db, hygiene_plan, case_with_visit_history):
        e = provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        q1 = provider.quote(
            db,
            QuoteRequest(
                case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id,
                therapist_id=hygiene_plan["therapist"].id, session_type="in_person", visit_seq=1,
            ),
        )
        appt1 = _make_appointment(db, hygiene_plan, case_with_visit_history, q1, start_offset_hours=1)

        provider.reserve(db, appt1.id, q1)
        row = db.query(InstEnrollment).filter(InstEnrollment.id == e.enrollment_id).first()
        assert row.reserved_count == 1

        provider.consume(db, appt1.id)
        db.refresh(row)
        assert row.used_count == 1

    def test_release_returns_to_reserved_not_a_new_state(self, db, hygiene_plan, case_with_visit_history):
        """C3 裁示：未到/取消不是「釋回」，是已預約還原為已預留——沒有第四種狀態。"""
        e = provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        q1 = provider.quote(
            db,
            QuoteRequest(
                case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id,
                therapist_id=hygiene_plan["therapist"].id, session_type="in_person", visit_seq=1,
            ),
        )
        appt1 = _make_appointment(db, hygiene_plan, case_with_visit_history, q1, start_offset_hours=1)
        provider.reserve(db, appt1.id, q1)

        provider.release(db, appt1.id, reason="未到-個案來電請假")
        row = db.query(InstEnrollment).filter(InstEnrollment.id == e.enrollment_id).first()
        assert row.reserved_count == 2  # 完整還原，個案仍保有兩次額度

    def test_consume_blocked_before_initial_visit(self, db, hygiene_plan):
        """08 決策 §8.3：流水號階段（未初診、無 case_number）可以 reserve，
        但不能 consume（真正產生金流），必須先完成初診。"""
        c = Case(
            name="尚未初診個案", therapist_id=hygiene_plan["therapist"].id, funding_source="institution",
            institution_id=hygiene_plan["institution"].id, status="initial",  # 無 case_number
        )
        db.add(c)
        db.flush()
        provider.enroll(db, case_id=c.id, plan_id=hygiene_plan["plan"].id)
        q1 = provider.quote(
            db,
            QuoteRequest(
                case_id=c.id, plan_id=hygiene_plan["plan"].id, therapist_id=hygiene_plan["therapist"].id,
                session_type="in_person", visit_seq=1,
            ),
        )
        appt = _make_appointment(db, hygiene_plan, c, q1, start_offset_hours=1)
        provider.reserve(db, appt.id, q1)  # 這步可以（booking 時間、預留額度）

        with pytest.raises(ValueError, match="尚未完成初診"):
            provider.consume(db, appt.id)  # 這步不行（要真正的病歷號才能產生金流）


class TestCaseClosure:
    def test_close_zeroes_reserved_and_locks_limit(self, db, hygiene_plan, case_with_visit_history):
        e = provider.enroll(db, case_id=case_with_visit_history.id, plan_id=hygiene_plan["plan"].id)
        row = db.query(InstEnrollment).filter(InstEnrollment.id == e.enrollment_id).first()
        row.reserved_count -= 1
        row.used_count += 1  # 做過一次
        db.flush()

        provider.close_case_enrollments(db, case_with_visit_history.id)
        db.refresh(row)
        assert row.reserved_count == 0
        assert row.quota_limit == row.used_count  # 上限鎖定在已使用量
        assert row.status == "closed"


class TestClaimContainer:
    """核銷案容器（07 §4.3，2026/09/07 定案）：容量是上限不是門檻，裝不滿也能送；
    收入認列（session_date）與核銷送件/入帳是兩條互不影響的時間軸。"""

    def _make_session_records(self, db, hygiene_plan, case, n=3):
        rows = []
        for i in range(n):
            sr = SessionRecord(
                session_date=date(2026, 7, 10 + i), case_id=case.id, therapist_id=hygiene_plan["therapist"].id,
                session_type="in_person", fee_category="counseling", amount=Decimal("1600"),
                payment_status="unpaid", funding_source="institution", plan_id=hygiene_plan["plan"].id,
                institution_payable=Decimal("1600"), case_payable=Decimal("0"),
            )
            db.add(sr)
            rows.append(sr)
        db.flush()
        return rows

    def test_submit_without_filling_capacity(self, db, hygiene_plan, case_with_visit_history):
        srs = self._make_session_records(db, hygiene_plan, case_with_visit_history, n=3)
        cc = claims_service.open_claim_case(
            db, claim_group_key=hygiene_plan["plan"].claim_group_key, grouping_mode="per_case_count", capacity=4
        )
        claims_service.attach_records(db, cc.id, [sr.id for sr in srs])

        cc = claims_service.submit(db, cc.id)
        assert cc.status == "submitted"
        assert cc.applied_amount == Decimal("4800")
        for sr in srs:
            db.refresh(sr)
            assert sr.payment_status == "claiming"

    def test_uncollected_query_empties_after_attach(self, db, hygiene_plan, case_with_visit_history):
        srs = self._make_session_records(db, hygiene_plan, case_with_visit_history, n=2)
        before = claims_service.list_uncollected(db, hygiene_plan["plan"].claim_group_key)
        assert len(before) == 2

        cc = claims_service.open_claim_case(db, claim_group_key=hygiene_plan["plan"].claim_group_key)
        claims_service.attach_records(db, cc.id, [sr.id for sr in srs])
        after = claims_service.list_uncollected(db, hygiene_plan["plan"].claim_group_key)
        assert after == []

    def test_income_recognition_month_unaffected_by_payment_month(self, db, hygiene_plan, case_with_visit_history):
        srs = self._make_session_records(db, hygiene_plan, case_with_visit_history, n=1)
        cc = claims_service.open_claim_case(db, claim_group_key=hygiene_plan["plan"].claim_group_key)
        claims_service.attach_records(db, cc.id, [sr.id for sr in srs])
        claims_service.submit(db, cc.id)

        cc = claims_service.record_payment(
            db, cc.id, received_date=date(2026, 9, 5), received_amount=Decimal("1600"),
            income_tax_amount=Decimal("160"), transfer_fee=Decimal("10"),
        )
        assert cc.net_received == Decimal("1430")
        db.refresh(srs[0])
        assert srs[0].session_date.month == 7  # 收入認列月份完全不受 9 月入帳影響
        assert srs[0].payment_status == "claimed"
