"""機構合約子系統的示範資料：從《260831新版-機構合約方案清冊.xlsx》
（32 個簽約單位、54 個方案）挑出 11 個涵蓋不同規則模式的代表方案，逐一
建成 institution/contract/plan/rate_rules，證明規則模型撐得住文件裡
描述的每一種變異（見 V2升級計畫 07_機構合約子系統架構.html §6.3 逐一驗算表）。

【誠實範圍聲明】這不是完整的 54 筆資料匯入，是「架構先起來」階段的示範
種子——目的是讓你能實際在畫面上操作、驗證規則模型，而不是要求你先手動
key 完 54 筆才能開始測試。涵蓋的 11 個模式：

    1. 衛生局市民    — visit_seq 分級定價（07 §1.1 模式③）
    2. 15-45青壯     — 單一固定價 + 方案層級額度池（次數）
    3. 國軍          — session_type 分級定價 + 方案層級額度池（金額 $149,000）
                        + 需要個案代號
    4. 南家扶        — session_type 分級定價（個別/親職/家族）
    5. 家防中心      — session_type 分級定價（個別/家族）+ 需要個案代號
    6. 市政府人事處  — 核銷容器 per_case_count=4（人事處系列的代表）
                        + 需要個案代號
    7. 脆弱家庭      — 核銷容器 per_case_count=8
    8. 教支中心      — compensation_mode=kickback（回扣）+ 需要個案代號
    9. 台南地院      — registered_hours_rule（登記時數≠實際時數）
   10. 聊心茶室      — price_source=therapist_rate（依心理師鐘點費）
   11. 鉅微借場地    — compensation_mode=none、counts_toward_quota=false
                        （借場地，無心理師勞務、無額度概念）

剩餘約 43 個方案的欄位資料完整記錄在 07 文件 §1（逐條列出定價/額度/核銷/
薪資/收據的原始描述），照這支檔案的寫法一個一個補即可——欄位形狀已經
被這 11 個涵蓋到的模式驗證過，不會再需要改 schema。

用法：
    DATABASE_URL=... .venv/bin/python -m app.institution.seed_plans
"""

import json
from decimal import Decimal

from app.database import SessionLocal
from app.institution.models.contract import InstContract
from app.institution.models.plan import InstPlan
from app.institution.models.quota_pool import InstQuotaPool
from app.institution.models.rate_rule import InstRateRule
from app.models.institution import Institution
from app.models.user import User


def _get_or_create_institution(db, name: str, code: str | None = None) -> Institution:
    inst = db.query(Institution).filter(Institution.name == name).first()
    if inst:
        return inst
    inst = Institution(name=name, code=code)
    db.add(inst)
    db.flush()
    return inst


def reset_plans(db) -> None:
    """清空機構合約子系統的所有資料表，依外鍵相依順序由下而上刪。

    給「重跑 seed」與假資料生成器用。刻意不碰 appointments/session_records
    ——那些是主系統的資料，若還有列引用 inst_plans，這裡會直接被外鍵擋下來，
    這是刻意的：寧可噴錯，也不要靜默刪掉別人的帳。
    """
    from sqlalchemy import text as _text
    for table in (
        "inst_claim_lines", "inst_claim_cases", "inst_enrollments",
        "inst_rate_rules", "inst_plans", "inst_quota_pools", "inst_contracts",
    ):
        db.execute(_text(f"DELETE FROM {table}"))
    db.flush()


def seed_plans(db=None, force: bool = False):
    """建立 11 個代表方案。

    `db` 可以傳入既有的 Session（測試、假資料生成器會這樣用），此時本函式
    不 commit 也不 close，交由呼叫端決定交易邊界；不傳則自己開一個、跑完
    commit + close（CLI 用法）。
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    admin = db.query(User).filter(User.role == "admin").first()
    created_by = admin.id if admin else None

    if db.query(InstPlan).first():
        if not force:
            print("已有方案資料，略過（要重跑請帶 force=True 或 --force）。")
            if owns_session:
                db.close()
            return
        reset_plans(db)

    # ── 1. 衛生局市民：visit_seq 分級 ───────────────────────────────────
    inst_health = _get_or_create_institution(db, "臺南市政府衛生局")
    c1 = InstContract(institution_id=inst_health.id, name="衛生局市民", created_by=created_by)
    db.add(c1)
    db.flush()
    p1 = InstPlan(
        contract_id=c1.id, name="衛生局市民", quota_unit="count", default_quota_limit_numeric=2,
        compensation_mode="commission", case_receipt_required=True, case_receipt_item_name="場地費",
        institution_receipt_required=False, claim_group_key="衛生局市民", claim_timing="monthly",
        claim_deadline_day=10,
        admin_checklist=json.dumps(["台南市民同意書(第一次)", "台南市民簽到表", "簡式量表(當次總分≧15分或自殺≧2分需轉介醫院)"], ensure_ascii=False),
        therapist_checklist=json.dumps(["台南市民同意書(第一次)", "台南市民簽到表", "視訊諮商截圖(畫面上需有身分證、日期時間)"], ensure_ascii=False),
        created_by=created_by,
    )
    db.add(p1)
    db.flush()
    db.add_all([
        InstRateRule(plan_id=p1.id, sort_order=1, when_json='{"visit_seq": 1}', unit_price=1600, case_payable=0, label="第一次（機構核銷$1600，個案免付）"),
        # 用 gte 而不是等於 2：額度延長過、或個案在自費與機構之間來回之後，
        # visit_seq 會超過 2，寫死等於 2 就沒有規則命中、報價 fallback 成 $0。
        InstRateRule(plan_id=p1.id, sort_order=2, when_json='{"visit_seq": {"gte": 2}}', unit_price=1400, case_payable=200, label="第二次起（機構核銷$1400，個案自付$200）"),
    ])

    # ── 2. 15-45青壯：單一固定價 + 方案層級額度池（次數）─────────────────
    inst_moh = _get_or_create_institution(db, "衛生福利部")
    pool2 = InstQuotaPool(contract_id=None, name="15-45青壯年度總額度", unit="count", total_limit=378)  # contract_id 補在下面
    c2 = InstContract(institution_id=inst_moh.id, name="15-45青壯", created_by=created_by)
    db.add(c2)
    db.flush()
    pool2.contract_id = c2.id
    db.add(pool2)
    db.flush()
    p2 = InstPlan(
        contract_id=c2.id, name="15-45青壯", quota_pool_id=pool2.id, quota_unit="count",
        default_quota_limit_numeric=3, compensation_mode="commission",
        case_receipt_required=True, case_receipt_item_name="場地費", institution_receipt_required=False,
        claim_group_key="15-45青壯", claim_timing="monthly", claim_deadline_day=15,
        created_by=created_by,
    )
    db.add(p2)
    db.flush()
    db.add(InstRateRule(plan_id=p2.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=400, label="每次固定"))

    # ── 3. 國軍：session_type 分級 + 額度池(金額) + 需要個案代號 ─────────
    inst_mnd = _get_or_create_institution(db, "國防部政治作戰局")
    c3 = InstContract(institution_id=inst_mnd.id, name="國軍心理照護方案", created_by=created_by)
    db.add(c3)
    db.flush()
    pool3 = InstQuotaPool(contract_id=c3.id, name="國軍年度總額度", unit="amount", total_limit=Decimal("149000"))
    db.add(pool3)
    db.flush()
    p3 = InstPlan(
        contract_id=c3.id, name="國軍-個別", quota_pool_id=pool3.id, quota_unit="count",
        default_quota_limit_numeric=6, requires_external_code=True, compensation_mode="commission",
        case_receipt_required=True, case_receipt_item_name="行政規費", institution_receipt_required=False,
        claim_group_key="國軍", claim_timing="monthly", claim_deadline_day=5, created_by=created_by,
    )
    db.add(p3)
    db.flush()
    db.add_all([
        InstRateRule(plan_id=p3.id, sort_order=1, when_json='{"consult_type": "individual"}', unit_price=1600, case_payable=400, label="個別諮商"),
        # 兜底：沒對到諮商型態時仍以個別價計，避免 resolve_rate 回 None → 報價 $0
        InstRateRule(plan_id=p3.id, sort_order=99, when_json="{}", unit_price=1600, case_payable=400, label="其餘情況（同個別價）"),
    ])
    # 國軍-講座/本島團輔/外島團輔：與國軍-個別共用 quota_pool_id 與 claim_group_key="國軍"，
    # 但額度各自獨立設定（依 07 §6.1「拆方案但共用池與核銷群組」的設計）。示範只建一個，
    # 其餘三個照此格式加即可。

    # ── 4. 南家扶：session_type 分級（個別/親職/家族）───────────────────
    inst_cwlf_s = _get_or_create_institution(db, "財團法人台灣兒童暨家庭扶助基金會_南區")
    c4 = InstContract(institution_id=inst_cwlf_s.id, name="南家扶", created_by=created_by)
    db.add(c4)
    db.flush()
    p4 = InstPlan(
        contract_id=c4.id, name="南家扶", quota_unit="count", default_quota_limit=None,  # 需評估
        requires_assessment=True, requires_external_code=True, compensation_mode="commission",
        case_receipt_required=False, institution_receipt_required=False,
        claim_group_key="南家扶", claim_timing="monthly", claim_deadline_day=5, created_by=created_by,
    )
    db.add(p4)
    db.flush()
    db.add_all([
        InstRateRule(plan_id=p4.id, sort_order=1, when_json='{"consult_type": "individual"}', unit_price=2000, case_payable=0, label="個別諮商"),
        InstRateRule(plan_id=p4.id, sort_order=2, when_json='{"consult_type": "parenting"}', unit_price=1000, case_payable=0, label="親職諮詢"),
        InstRateRule(plan_id=p4.id, sort_order=3, when_json='{"consult_type": "family"}', unit_price=2400, case_payable=0, label="家族諮商"),
        InstRateRule(plan_id=p4.id, sort_order=99, when_json="{}", unit_price=2000, case_payable=0, label="其餘情況（同個別價）"),
        # 「無事先請假爽約費 $200」是未到事件產生的費用，不是預約當下的報價，
        # 見 07 §6.3 附註：不做失約費（第①組定案），此規則暫不建立。
    ])

    # ── 5. 家防中心：consult_type（諮商型態）分級 + 需要個案代號 ──────────
    inst_dv = _get_or_create_institution(db, "臺南市政府家庭暴力暨性侵害防治中心")
    c5 = InstContract(institution_id=inst_dv.id, name="家防中心", created_by=created_by)
    db.add(c5)
    db.flush()
    p5 = InstPlan(
        contract_id=c5.id, name="家防中心", quota_unit="count", default_quota_limit_numeric=12,
        requires_external_code=True, compensation_mode="commission",
        case_receipt_required=False, institution_receipt_required=False,
        claim_group_key="家防中心", claim_timing="monthly", claim_deadline_day=15, created_by=created_by,
    )
    db.add(p5)
    db.flush()
    db.add_all([
        InstRateRule(plan_id=p5.id, sort_order=1, when_json='{"consult_type": "individual"}', unit_price=1400, case_payable=0, label="個別/hr"),
        InstRateRule(plan_id=p5.id, sort_order=2, when_json='{"consult_type": "family"}', unit_price=2000, case_payable=0, label="家族/hr"),
        InstRateRule(plan_id=p5.id, sort_order=99, when_json="{}", unit_price=1400, case_payable=0, label="其餘情況（同個別價）"),
    ])

    # ── 6. 市政府人事處：核銷容器 per_case_count=4（人事處系列代表）──────
    inst_hr = _get_or_create_institution(db, "台南市政府人事處")
    c6 = InstContract(institution_id=inst_hr.id, name="市政府人事處", created_by=created_by)
    db.add(c6)
    db.flush()
    p6 = InstPlan(
        contract_id=c6.id, name="市政府人事處", quota_unit="count", default_quota_limit_numeric=4,
        requires_external_code=True, compensation_mode="commission",
        case_receipt_required=False, institution_receipt_required=True, institution_receipt_item_name="諮商鐘點費",
        claim_group_key="人事處_市政府", claim_timing="threshold", claim_grouping_mode="per_case_count",
        claim_capacity=4, created_by=created_by,
    )
    db.add(p6)
    db.flush()
    db.add(InstRateRule(plan_id=p6.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=0, label="每次固定"))
    # 衛生局人事處/教育局人事處/環保局人事處/消防局人事處/文化局人事處/民政局人事處
    # 六個局處照此格式各建一個 InstPlan，claim_group_key 各自獨立（不同局處分開核銷）。

    # ── 7. 脆弱家庭：核銷容器 per_case_count=8 ───────────────────────────
    inst_social = _get_or_create_institution(db, "臺南市政府社會局")
    c7 = InstContract(institution_id=inst_social.id, name="脆弱家庭", created_by=created_by)
    db.add(c7)
    db.flush()
    p7 = InstPlan(
        contract_id=c7.id, name="脆弱家庭", quota_unit="count", default_quota_limit_numeric=8,
        compensation_mode="commission", case_receipt_required=False, institution_receipt_required=False,
        claim_group_key="脆弱家庭", claim_timing="threshold", claim_grouping_mode="per_case_count",
        claim_capacity=8, created_by=created_by,
    )
    db.add(p7)
    db.flush()
    db.add(InstRateRule(plan_id=p7.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=0, label="每次固定"))

    # ── 8. 教支中心：回扣（kickback）+ 需要個案代號 ──────────────────────
    inst_edu_center = _get_or_create_institution(db, "教育部_教師諮商輔導支持中心")
    c8 = InstContract(institution_id=inst_edu_center.id, name="教支中心", created_by=created_by)
    db.add(c8)
    db.flush()
    p8 = InstPlan(
        contract_id=c8.id, name="教支中心", quota_unit="count", default_quota_limit_numeric=6,
        requires_external_code=True, compensation_mode="kickback",
        case_receipt_required=False, institution_receipt_required=False,
        claim_group_key="教支中心", claim_timing="monthly", claim_deadline_day=15, created_by=created_by,
    )
    db.add(p8)
    db.flush()
    db.add(InstRateRule(plan_id=p8.id, sort_order=1, when_json="{}", unit_price=2000, case_payable=0, label="每次固定；機構直接匯給心理師，心理師依抽成回繳慈恩"))

    # ── 9. 台南地院：登記時數 ≠ 實際時數 ─────────────────────────────────
    inst_court = _get_or_create_institution(db, "臺灣臺南地方法院")
    c9 = InstContract(institution_id=inst_court.id, name="台南地院", created_by=created_by)
    db.add(c9)
    db.flush()
    p9 = InstPlan(
        contract_id=c9.id, name="台南地院", quota_unit="count", default_quota_limit=None,
        requires_assessment=True, compensation_mode="commission",
        case_receipt_required=False, institution_receipt_required=True, institution_receipt_item_name="諮商鐘點費",
        claim_group_key="台南地院", claim_timing="monthly", claim_deadline_day=20,
        # 宣告式規則，收納時由 claims/service.attach_records() 自動套用。
        # 語意：實際 1 小時 $1600 → 核銷登記 2 小時、每小時 $800（機構預算
        # 科目的單價是固定的，只能用時數湊出實收金額）。
        # 原本這欄是自由文字備忘，行政得自己心算再手動填申請金額。
        registered_hours_rule='{"multiplier": 2, "registered_unit_price": 800, "note": "實際1小時$1600 → 登記2小時@$800"}',
        created_by=created_by,
    )
    db.add(p9)
    db.flush()
    db.add(InstRateRule(plan_id=p9.id, sort_order=1, when_json="{}", unit_price=1600, case_payable=0, label="實際收費（核銷時自動換算為登記時數）"))

    # ── 10. 聊心茶室：依心理師鐘點費 ─────────────────────────────────────
    inst_tea = _get_or_create_institution(db, "HealYou_聊心茶室")
    c10 = InstContract(institution_id=inst_tea.id, name="聊心茶室", created_by=created_by)
    db.add(c10)
    db.flush()
    p10 = InstPlan(
        contract_id=c10.id, name="聊心茶室", quota_unit="count", default_quota_limit=None,
        compensation_mode="commission", case_receipt_required=False, institution_receipt_required=False,
        claim_group_key="聊心茶室", claim_timing="monthly", created_by=created_by,
    )
    db.add(p10)
    db.flush()
    db.add(InstRateRule(plan_id=p10.id, sort_order=1, when_json="{}", price_source="therapist_rate", case_payable=0, label="依心理師鐘點費"))

    # ── 11. 鉅微借場地：無心理師勞務、無額度概念 ─────────────────────────
    inst_jw = _get_or_create_institution(db, "鉅微管理顧問股份有限公司")
    c11 = InstContract(institution_id=inst_jw.id, name="鉅微借場地", created_by=created_by)
    db.add(c11)
    db.flush()
    p11 = InstPlan(
        contract_id=c11.id, name="鉅微/借場地", quota_unit="count", counts_toward_quota=False,
        compensation_mode="none", case_receipt_required=False,
        institution_receipt_required=True, institution_receipt_item_name="場地費",
        claim_group_key="鉅微借場地", claim_timing="monthly", created_by=created_by,
    )
    db.add(p11)
    db.flush()
    db.add(InstRateRule(plan_id=p11.id, sort_order=1, when_json="{}", unit_price=500, case_payable=0, label="每小時$500，可手動改，允許$0"))

    if owns_session:
        db.commit()
    else:
        db.flush()
    print("已建立 11 個代表方案（衛生局市民/15-45青壯/國軍/南家扶/家防中心/市政府人事處/")
    print("脆弱家庭/教支中心/台南地院/聊心茶室/鉅微借場地）。")
    print("剩餘方案資料見 07_機構合約子系統架構.html §1，照本檔案格式續補。")
    if owns_session:
        db.close()


if __name__ == "__main__":
    import sys
    seed_plans(force="--force" in sys.argv)
