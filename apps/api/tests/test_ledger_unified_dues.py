"""GET /ledger/self-pay-unpaid 的統一自付款查詢。見 09 §1.4a 的裁示：

「機構案有時候會需要自費款……那這 400 元自費款也要納入整個自費流程，
一般來說當日就要結清」——這支端點過去只認 funding_source=='self_pay'，
機構案的 case_payable 完全不會出現在「未收」清單。這裡驗證修正後的行為：
不分 funding_source，只認「個案自付額收了沒」。
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from tests.test_payment_receipt import _checked_in_institution_appt, _checked_in_self_pay_appt, _seed

client = TestClient(app)


class TestUnifiedSelfPayDues:
    def test_institution_case_payable_appears_before_collection(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_institution_appt(db, ctx, case_payable=Decimal("400"), institution_payable=Decimal("1200"))
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        r = client.get("/ledger/self-pay-unpaid", headers=headers)
        assert r.status_code == 200, r.text
        ids = [row["appointment_id"] for row in r.json()]
        # 找出剛剛那筆 session_record 對應的 appointment_id
        from app.models.session_record import SessionRecord
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt_id).first()
        assert sr is not None
        assert appt_id in ids, "機構案的個案自付額應該出現在統一未收清單裡"

    def test_institution_case_payable_disappears_after_collection(self, db, http_db):
        ctx = _seed(db)
        appt_id = _checked_in_institution_appt(db, ctx, case_payable=Decimal("400"), institution_payable=Decimal("1200"))
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}
        client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})

        r = client.get("/ledger/self-pay-unpaid", headers=headers)
        ids = [row["appointment_id"] for row in r.json()]
        assert appt_id not in ids, "收款後（copay_collected_at 有值）不該再出現在未收清單"

    def test_institution_full_coverage_never_appears(self, db, http_db):
        """機構全額（case_payable=0）：個案免收，本來就不該進未收清單。"""
        ctx = _seed(db)
        appt_id = _checked_in_institution_appt(db, ctx, case_payable=Decimal("0"), institution_payable=Decimal("1600"))
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        r = client.get("/ledger/self-pay-unpaid", headers=headers)
        ids = [row["appointment_id"] for row in r.json()]
        assert appt_id not in ids

    def test_pure_self_pay_still_works(self, db, http_db):
        """回歸測試：純自費案的既有行為（payment_status 判斷）不受影響。"""
        ctx = _seed(db)
        appt_id = _checked_in_self_pay_appt(db, ctx, amount=2000)
        headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

        r = client.get("/ledger/self-pay-unpaid", headers=headers)
        ids = [row["appointment_id"] for row in r.json()]
        assert appt_id in ids

        client.post(f"/appointments/{appt_id}/payment-step", headers=headers, json={"payment_method": "cash"})
        r2 = client.get("/ledger/self-pay-unpaid", headers=headers)
        ids2 = [row["appointment_id"] for row in r2.json()]
        assert appt_id not in ids2
