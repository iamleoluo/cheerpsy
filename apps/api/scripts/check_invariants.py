"""資料一致性檢查器。整個資料集是否「照規則長出來」的唯一判準。

用法：
    DATABASE_URL=... .venv/bin/python -m scripts.check_invariants
    DATABASE_URL=... .venv/bin/python -m scripts.check_invariants --verbose

為什麼是 SQL 不是 Python：這些都是對整個資料集的集合斷言，用 SQL 寫出來
可以原封不動貼進 psql 追問題，而且不必把整張表拉進記憶體。
`資料庫結構與資料轉換規範.md` §6 已經有這個做法的雛形。

每條檢查回傳「違規的列」，一列都沒有才算過。任何一條有命中就以非零離開，
所以可以直接接在假資料生成器最後一步、或放進 CI。

新增檢查時：加一個 Check(...) 進 CHECKS，說明欄請寫「為什麼這條會壞」，
不要只寫「應該要相等」——半年後看的人需要知道違反時代表哪個流程漏了。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from sqlalchemy import text

os.environ.setdefault("DATABASE_URL", "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy")

from app.database import SessionLocal  # noqa: E402


@dataclass
class Check:
    key: str
    title: str
    why: str
    sql: str


# 台北日期的統一寫法。session_records.session_date 是台北日期（見 utils/tz.py），
# 而 time_range 存的是 timestamptz，所以比對前要先轉時區。
TPE = "AT TIME ZONE 'Asia/Taipei'"

CHECKS: list[Check] = [
    Check(
        "quota_identity",
        "額度三態恆等式",
        "上限＋延長 必須等於 已使用＋已預留＋已預約。破了代表某條路徑扣了額度卻沒還"
        "（取消/刪除/未到），合約面板的三色長條會愈算愈偏。",
        f"""
        SELECT e.id AS enrollment_id, e.case_id, e.plan_id,
               e.quota_limit, e.extended_count, e.used_count, e.reserved_count,
               (SELECT count(*) FROM appointments a
                 WHERE a.plan_id = e.plan_id AND a.case_id = e.case_id
                   AND a.status = 'booked'
                   AND (a.check_in_status IS NULL OR a.check_in_status <> 'no_show')) AS booked
          FROM inst_enrollments e
         WHERE e.quota_limit IS NOT NULL
           AND e.status <> 'closed'
           AND e.quota_limit + COALESCE(e.extended_count, 0)
             <> e.used_count + e.reserved_count
              + (SELECT count(*) FROM appointments a
                  WHERE a.plan_id = e.plan_id AND a.case_id = e.case_id
                    AND a.status = 'booked'
                    AND (a.check_in_status IS NULL OR a.check_in_status <> 'no_show'))
        """,
    ),
    Check(
        "pool_consumed",
        "合約額度池消耗量",
        "池的 consumed_total 必須等於底下所有方案「已執行且未作廢」場次的加總。"
        "不符代表 consume/unconsume 有一邊漏了，年度池餘額會失真。",
        """
        SELECT p.id AS pool_id, p.name, p.unit, p.consumed_total, x.expected
          FROM inst_quota_pools p
          JOIN LATERAL (
                SELECT COALESCE(SUM(CASE WHEN p.unit = 'amount'
                                         THEN COALESCE(sr.institution_payable, 0)
                                         ELSE 1 END), 0) AS expected
                  FROM session_records sr
                  JOIN inst_plans pl ON pl.id = sr.plan_id
                 WHERE pl.quota_pool_id = p.id
                   AND sr.is_void = false
                   AND sr.fee_category <> 'no_show_fee'
               ) x ON true
         WHERE p.consumed_total <> x.expected
        """,
    ),
    Check(
        "closed_case_enrollment",
        "結案個案不得有進行中的機構方案",
        "close_case() 必須連帶關閉 inst_enrollments，否則結案個案的額度被永久佔住、"
        "方案總量看起來永遠回不來。",
        """
        SELECT c.id AS case_id, c.name, c.case_number, e.id AS enrollment_id, e.status
          FROM cases c JOIN inst_enrollments e ON e.case_id = c.id
         WHERE c.status = 'closed' AND e.status <> 'closed'
        """,
    ),
    Check(
        "session_date_taipei",
        "場次日期＝預約起始的台北日期",
        "session_date 用的是台北日期（utils/tz.to_local_date）。若某條路徑改用 UTC 日期，"
        "深夜時段的場次會被歸到前一天，日報表對帳就會憑空多/少一天。",
        f"""
        SELECT sr.id AS session_record_id, sr.session_date,
               (lower(a.time_range) {TPE})::date AS expected
          FROM session_records sr JOIN appointments a ON a.id = sr.appointment_id
         WHERE sr.session_date <> (lower(a.time_range) {TPE})::date
        """,
    ),
    Check(
        "arrived_has_record",
        "已報到必有帳冊紀錄",
        "check_in_status='arrived' 代表場次成立，一定要有對應的 session_record，"
        "否則這場不會進日報表、不會計酬、也不會被核銷。",
        """
        SELECT a.id AS appointment_id, a.appointment_number, a.status, a.check_in_status
          FROM appointments a
         WHERE a.check_in_status = 'arrived'
           AND NOT EXISTS (SELECT 1 FROM session_records sr WHERE sr.appointment_id = a.id)
        """,
    ),
    Check(
        "no_show_has_no_session",
        "未到／取消不得產生諮商場次",
        "未到只能產生 fee_category='no_show_fee' 的機構補助紀錄（09 §7.1），"
        "不可以有一般的 counseling 場次；取消的預約則完全不該有紀錄。",
        """
        SELECT a.id AS appointment_id, a.appointment_number, a.status, a.check_in_status,
               sr.id AS session_record_id, sr.fee_category
          FROM appointments a JOIN session_records sr ON sr.appointment_id = a.id
         WHERE (a.check_in_status = 'no_show' AND sr.fee_category <> 'no_show_fee')
            OR (a.status = 'cancelled')
        """,
    ),
    Check(
        "room_overlap",
        "同一診間不得時段重疊",
        "excl_room_time_overlap 這條 GIST 約束會擋，但只擋 status<>'cancelled'。"
        "這裡再驗一次，順便涵蓋資料是用 SQL 直灌進去的情況。",
        """
        SELECT a.id AS a_id, b.id AS b_id, a.room_id, a.time_range::text AS a_range, b.time_range::text AS b_range
          FROM appointments a JOIN appointments b
            ON a.room_id = b.room_id AND a.id < b.id AND a.time_range && b.time_range
         WHERE a.room_id IS NOT NULL
           AND a.status <> 'cancelled' AND b.status <> 'cancelled'
        """,
    ),
    Check(
        "receipt_no_unique",
        "收據號不得跨表重複",
        "session_records.receipt_no 與 receipts.receipt_no 各自 unique，但兩張表之間"
        "沒有約束。舊程式碼兩邊各數各的序號，同一天會產出一模一樣的字串。",
        """
        SELECT receipt_no, count(*) AS n FROM (
            SELECT receipt_no FROM session_records WHERE receipt_no IS NOT NULL
            UNION ALL
            SELECT receipt_no FROM receipts WHERE receipt_no IS NOT NULL AND status = 'issued'
        ) x GROUP BY receipt_no HAVING count(*) > 1
        """,
    ),
    Check(
        "payable_split",
        "個案自付＋機構請款＝總額",
        "報價快照的兩份金額加起來必須等於場次總額，否則收款收錯、核銷也請錯。",
        """
        SELECT sr.id AS session_record_id, sr.amount, sr.case_payable, sr.institution_payable
          FROM session_records sr
         WHERE sr.case_payable IS NOT NULL AND sr.institution_payable IS NOT NULL
           AND sr.case_payable + sr.institution_payable <> sr.amount
        """,
    ),
    Check(
        "zero_priced_plan_session",
        "機構方案場次不得報價 $0",
        "有 plan_id 卻金額為 0，代表沒有任何費率規則命中、fallback 成 0"
        "（07 §6.2 的維度撞名就是這樣造成的）。借場地方案例外，它本來就允許 $0。",
        """
        SELECT sr.id AS session_record_id, sr.session_date, pl.name AS plan_name, sr.amount
          FROM session_records sr JOIN inst_plans pl ON pl.id = sr.plan_id
         WHERE sr.amount = 0 AND sr.is_void = false
           AND pl.compensation_mode <> 'none'
        """,
    ),
    Check(
        "claim_line_uniqueness",
        "一筆場次只能被一個核銷案收納",
        "uq_claim_line_session_record 會擋，這裡連同「已收納的紀錄不該是作廢的」一起驗。",
        """
        SELECT cl.id AS claim_line_id, cl.session_record_id, sr.is_void
          FROM inst_claim_lines cl JOIN session_records sr ON sr.id = cl.session_record_id
         WHERE sr.is_void = true
        """,
    ),
    Check(
        "submitted_claim_status",
        "已送出的核銷案，成員紀錄狀態要跟上",
        "submit() 會把每一筆 payment_status 設成 claiming、record_payment() 設成 claimed。"
        "對不上代表有人繞過 service 直接改狀態。",
        """
        SELECT cc.id AS claim_case_id, cc.claim_no, cc.status, sr.id AS session_record_id, sr.payment_status
          FROM inst_claim_cases cc
          JOIN inst_claim_lines cl ON cl.claim_case_id = cc.id
          JOIN session_records sr ON sr.id = cl.session_record_id
         WHERE (cc.status = 'submitted' AND sr.payment_status <> 'claiming')
            OR (cc.status = 'closed' AND sr.payment_status <> 'claimed')
        """,
    ),
    Check(
        "payout_total",
        "酬勞總額＝成員場次加總",
        "回扣制要記成負的、作廢不計、優待要從基數扣（07 §8.2）。"
        "對不上代表 payouts 的計算與 payout_line_amount() 又各走各的了。",
        """
        SELECT tp.id AS payout_id, tp.therapist_id, tp.payout_month, tp.total_amount, x.expected
          FROM therapist_payouts tp
          JOIN LATERAL (
                SELECT COALESCE(SUM(
                    CASE WHEN sr.is_void THEN 0
                         WHEN COALESCE(sr.compensation_mode, 'commission') = 'none' THEN 0
                         WHEN sr.compensation_mode = 'kickback'
                           THEN -(COALESCE(sr.commissionable_base, sr.amount - COALESCE(sr.discount_amount, 0))
                                  * (1 - COALESCE(sr.commission_rate_used, 0.70)))
                         ELSE COALESCE(sr.commissionable_base, sr.amount - COALESCE(sr.discount_amount, 0))
                              * COALESCE(sr.commission_rate_used, 0.70) + COALESCE(sr.outcall_bonus, 0)
                    END), 0) AS expected
                  FROM payout_details pd JOIN session_records sr ON sr.id = pd.session_id
                 WHERE pd.payout_id = tp.id
               ) x ON true
         WHERE abs(tp.total_amount - x.expected) > 0.05
        """,
    ),
    Check(
        "appointment_number_date",
        "預約編號的日期段＝起始時間的台北日期",
        "R-{YYYYMMDD}-{代碼}-{流水}。日期段對不上代表配號時傳錯日期，"
        "行政用編號找當天的預約會找不到。",
        f"""
        SELECT a.id AS appointment_id, a.appointment_number,
               to_char((lower(a.time_range) {TPE})::date, 'YYYYMMDD') AS expected_date
          FROM appointments a
         WHERE a.appointment_number LIKE 'R-%'
           AND split_part(a.appointment_number, '-', 2)
               <> to_char((lower(a.time_range) {TPE})::date, 'YYYYMMDD')
        """,
    ),
    Check(
        "case_number_requires_ongoing",
        "有病歷號⇔已轉正式",
        "兩段式編號（資料庫規範 §4.1）：病歷號只在 activate_case 產生，"
        "所以有號的一定不是 initial，而 ongoing/closed 的一定要有號。",
        """
        SELECT id AS case_id, name, status, case_number
          FROM cases
         WHERE (case_number IS NOT NULL AND status = 'initial')
            OR (case_number IS NULL AND status IN ('ongoing', 'closed'))
        """,
    ),
    Check(
        "institution_case_has_number",
        "消耗過機構額度的個案必須有病歷號",
        "adapter.consume() 的前置條件（07 §8.3）：沒有正式病歷號不能真正消耗額度。",
        """
        SELECT DISTINCT c.id AS case_id, c.name, c.status
          FROM cases c JOIN inst_enrollments e ON e.case_id = c.id
         WHERE e.used_count > 0 AND c.case_number IS NULL
        """,
    ),
    Check(
        "couple_membership",
        "伴侶案必須恰好兩位成員",
        "case_type='couple' 是一個收費單位，兩位成員各自仍是獨立個案（資料庫規範 §4.3）。",
        """
        SELECT c.id AS case_id, c.name, count(cm.id) AS members
          FROM cases c LEFT JOIN couple_members cm ON cm.couple_case_id = c.id
         WHERE c.case_type = 'couple'
         GROUP BY c.id, c.name HAVING count(cm.id) <> 2
        """,
    ),
    Check(
        "orphan_rate_rule_keys",
        "費率規則的條件鍵必須被報價引擎認得",
        "pricing.rule_matches() 對未知 key 是寬容跳過，寫錯 key 的規則會靜默變成"
        "「命中全部」而不是報錯——價錢就錯了，畫面上看不出來。",
        """
        SELECT r.id AS rule_id, r.label, k AS unknown_key
          FROM inst_rate_rules r,
               LATERAL jsonb_object_keys(r.when_json::jsonb) AS k
         WHERE r.when_json IS NOT NULL AND r.when_json <> '{}'
           AND k NOT IN ('session_type','consult_type','visit_seq','duration_min',
                         'location_kind','time_band','sub_unit')
        """,
    ),
]


def run(verbose: bool = False) -> int:
    db = SessionLocal()
    failures = 0
    try:
        for chk in CHECKS:
            rows = db.execute(text(chk.sql)).mappings().all()
            if rows:
                failures += 1
                print(f"\n✗ [{chk.key}] {chk.title} — {len(rows)} 筆違規")
                print(f"  {chk.why}")
                for r in rows[:10]:
                    print(f"    {dict(r)}")
                if len(rows) > 10:
                    print(f"    …另有 {len(rows) - 10} 筆")
            elif verbose:
                print(f"✓ [{chk.key}] {chk.title}")
    finally:
        db.close()

    print()
    if failures:
        print(f"❌ {failures}/{len(CHECKS)} 條不變量被違反")
        return 1
    print(f"✅ {len(CHECKS)} 條不變量全部通過")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="檢查資料集是否符合所有跨表不變量")
    ap.add_argument("--verbose", "-v", action="store_true", help="通過的檢查也印出來")
    sys.exit(run(verbose=ap.parse_args().verbose))
