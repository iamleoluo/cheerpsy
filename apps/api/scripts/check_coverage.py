"""覆蓋率檢查器。假資料「有沒有把系統的每條規則都走到」的唯一判準。

用法：
    DATABASE_URL=... PYTHONPATH=. .venv/bin/python scripts/check_coverage.py
    DATABASE_URL=... PYTHONPATH=. .venv/bin/python scripts/check_coverage.py --verbose

────────────────────────────────────────────────────────────────────────────
這支跟 check_invariants.py 問的是**相反**的問題：

    不變量檢查器   資料**有沒有壞**          失敗＝查到違規列
    覆蓋率檢查器   規則**有沒有被走到**      失敗＝某分支樣本數 < 門檻

為什麼需要它：「整格轉灰有三條規則、但只實作了一條」那個 bug 能活那麼久，
不是因為沒人看，是因為**另外兩條分支從來沒有資料經過**。一條沒有資料走過的
分支，寫錯了也不會有任何東西叫。不變量檢查不到——資料本身沒壞，它只是不存在。

所以這支同時是兩個東西：
  ① 假資料的驗收標準（13 §5）
  ② 一份**可執行的業務分支清單**。每加一條分支就加一條檢查，
     等於強迫回答「這條分支要怎麼被看到」——那正是最容易漏掉的一步。

門檻怎麼訂：不是「有一筆就算數」。要能在畫面上被看見、能驗得出錯價錯帳，
所以常見分支抓幾十到上百，罕見分支至少十幾筆。門檻寫在每條的 min_count。
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from sqlalchemy import text

os.environ.setdefault("DATABASE_URL", "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy")

from app.database import SessionLocal  # noqa: E402

TPE = "AT TIME ZONE 'Asia/Taipei'"


@dataclass
class Cov:
    key: str
    area: str
    title: str
    why: str
    min_count: int
    sql: str  # 必須回傳單一數字


CHECKS: list[Cov] = [
    # ══ 個案 ══════════════════════════════════════════════════════════
    Cov("case_initial", "個案", "暫存案（尚未轉正式）",
        "兩段式編號的第一段。沒有樣本的話，「暫存 → 補身分證 → 產生病歷號」整條流程"
        "在畫面上完全看不到——包括剛做好的初診報到。",
        8, "SELECT count(*) FROM cases WHERE status='initial'"),
    Cov("case_churn", "個案", "流失預警",
        "/reports 的流失預警分頁直接讀這個狀態。沒有資料那一頁就是空的。",
        12, "SELECT count(*) FROM cases WHERE status='churn_risk'"),
    Cov("case_closed", "個案", "已結案",
        "結案要連帶關閉機構方案（P1 修過的 bug）。沒有已結案個案就驗不到那條路徑。",
        20, "SELECT count(*) FROM cases WHERE status='closed'"),
    Cov("case_billing_monthly", "個案", "月結個案",
        "「整格轉灰」三條規則之一：自費月結按完已到就轉灰、不需收款開據。"
        "第一版就是因為沒有樣本，把月結案判成待處理。",
        30, "SELECT count(*) FROM cases WHERE billing_cycle='monthly'"),
    Cov("case_billing_multiple", "個案", "多次結個案",
        "第三種結帳週期。與次結的差別在核銷容器的裝填方式。",
        15, "SELECT count(*) FROM cases WHERE billing_cycle='multiple'"),
    Cov("case_designated", "個案", "指定心理師",
        "/reports 的進案統計有一整組「指定」欄位。比例太低那四欄會全是「—」，"
        "那個分組看起來就像多餘的。",
        50, "SELECT count(*) FROM cases WHERE is_designated"),
    Cov("case_couple_self", "個案", "自費伴侶案",
        "伴侶案自己是一筆 case、擁有合療預約與帳務（合併一筆）。",
        6, "SELECT count(*) FROM cases WHERE case_type='couple' AND funding_source='self_pay'"),
    Cov("case_couple_inst", "個案", "機構伴侶案（逐人核銷）",
        "07 的重要設計：機構核銷以人為單位，伴侶案沒有真人身分不能當核銷對象，"
        "所以合療預約要選付款方。**現在完全是 0，這個設計在畫面上看不到**。",
        6, "SELECT count(*) FROM cases WHERE case_type='couple' AND funding_source='institution'"),

    # ══ 預約 ══════════════════════════════════════════════════════════
    Cov("appt_density_weekday", "預約", "平日單日現場場次密度",
        "空間利用率目標三到五成（13 §2.1）。密度不足的話，所有為密度做的設計"
        "——四行結構、整格轉灰、最後一次標黃、跨格 rowSpan——在空白日曆上看不出價值。"
        "這裡量的是「有多少個工作日達到 40 筆以上」。",
        150, f"""
        SELECT count(*) FROM (
          SELECT (lower(a.time_range) {TPE})::date AS d, count(*) AS n
            FROM appointments a
           WHERE a.status <> 'cancelled' AND a.session_type = 'in_person'
           GROUP BY 1 HAVING count(*) >= 40
        ) x"""),
    Cov("appt_future", "預約", "未來預約",
        "「待報到」、排班檢視、週檢視都靠它。只有幾十筆的話往後翻兩天就沒東西了。",
        600, "SELECT count(*) FROM appointments WHERE lower(time_range) > now() AND status='booked'"),
    Cov("appt_no_show", "預約", "未到",
        "未到要還原額度、不轉 cancelled（01 §C3）、格子維持紅底不轉灰。",
        80, "SELECT count(*) FROM appointments WHERE check_in_status='no_show'"),
    Cov("appt_cancelled", "預約", "已取消",
        "取消要還額度（P1 修過的 bug：取消不還額度，三態恆等式每次少 1）。",
        80, "SELECT count(*) FROM appointments WHERE status='cancelled'"),
    Cov("appt_duration_adjusted", "預約", "加時（實際時數調整）",
        "P4 的加時功能：回寫 time_range、撞到鄰場要擋（01 §C1）。",
        40, "SELECT count(*) FROM appointments WHERE actual_start IS NOT NULL"),
    Cov("appt_video_pending", "預約", "視訊連結待轉發",
        "待轉發與已轉發是兩個不同畫面狀態。只有已轉發的話，「該寄連結了」那個提醒看不到。",
        15, "SELECT count(*) FROM appointments WHERE video_link IS NOT NULL AND video_forwarded_at IS NULL"),
    Cov("appt_leave", "預約", "個案請假",
        "P4 的請假流程，與「未到」是不同的東西。",
        20, "SELECT count(*) FROM appointments WHERE leave_at IS NOT NULL"),
    Cov("appt_first_visit_pending", "預約", "待報到的初診",
        "媒合案停在 booked、預約還沒報到。**demo 初診報到時要點得到格子**，"
        "現在是 0 —— 那個剛做好的「已到·補個資」按鈕在畫面上根本找不到。",
        5, """
        SELECT count(*) FROM referrals r JOIN appointments a ON a.id = r.appointment_id
         WHERE r.status='booked' AND a.status='booked' AND a.check_in_status='pending'"""),

    # ══ 型式 × 諮商型態（費率規則的兩條計價軸）══════════════════════
    *[
        Cov(f"mix_{st}_{ct}", "型式組合", f"{label_st} × {label_ct}",
            "費率規則依 session_type 與 consult_type 兩軸計價（D1 新增的維度）。"
            "組合樣本太少就驗不出錯價——南家扶／家防中心原本永遠報價 $0 就是這樣沒被發現的。"
            "視訊與外展量本來就少，這幾格要**刻意配**而不是等機率撒到。",
            12, f"SELECT count(*) FROM appointments WHERE session_type='{st}' AND consult_type='{ct}'")
        for st, label_st in [("in_person", "現場"), ("online", "視訊"), ("outdoor", "外展")]
        for ct, label_ct in [("individual", "個別"), ("couple", "伴侶"),
                             ("family", "家族"), ("parenting", "親職")]
    ],

    # ══ 機構方案 ══════════════════════════════════════════════════════
    Cov("plan_all_used", "機構方案", "每個方案都有人用",
        "11 個方案裡有一個（鉅微／借場地）用量是 0。一個從來沒被走過的方案，"
        "它的費率、額度、核銷行為全部沒被驗證過。這裡量的是「用量 < 10 筆的方案數」，"
        "**必須是 0**。",
        0, """
        SELECT count(*) FROM (
          SELECT p.id FROM inst_plans p
            LEFT JOIN appointments a ON a.plan_id = p.id
           GROUP BY p.id HAVING count(a.id) < 10
        ) x""", ),
    Cov("plan_kickback", "機構方案", "回饋制（kickback）場次",
        "金流方向與抽成相反：心理師先收到全額、欠診所回饋金，酬勞單上是**扣項**。"
        "沒有樣本的話「我的酬勞」B 區整區不會出現。",
        40, "SELECT count(*) FROM session_records WHERE compensation_mode='kickback' AND NOT is_void"),
    Cov("plan_none_comp", "機構方案", "不計酬場次",
        "借場地等沒有心理師勞務的場次。酬勞單 C 區。",
        20, "SELECT count(*) FROM session_records WHERE compensation_mode='none' AND NOT is_void"),
    Cov("plan_per_case_count", "機構方案", "per_case_count 核銷容器",
        "與期間制不同：每滿 N 次自動收納成一個核銷案。",
        20, """
        SELECT count(*) FROM session_records s JOIN inst_plans p ON p.id = s.plan_id
         WHERE p.claim_grouping_mode='per_case_count'"""),
    Cov("plan_external_code", "機構方案", "需要外部個案代號的方案",
        "沒填代號會擋下核銷（P5 的 requires_external_code）。個案代號事後登錄那個"
        "修正就是為它做的。",
        20, """
        SELECT count(*) FROM inst_enrollments e JOIN inst_plans p ON p.id = e.plan_id
         WHERE p.requires_external_code"""),
    Cov("pool_count", "機構方案", "次數池",
        "合約層級的共用額度（15-45 青壯 378 次型）。與個人額度是兩層。",
        1, "SELECT count(*) FROM inst_quota_pools WHERE unit='count'"),
    Cov("pool_amount", "機構方案", "金額池",
        "國軍 $149,000 型：扣的是錢不是次數，進度條的算法不一樣。",
        1, "SELECT count(*) FROM inst_quota_pools WHERE unit='amount'"),
    Cov("quota_exhausted", "機構方案", "額度用罄的個案",
        "額度見底的畫面（整格標黃「最後一次」、合約面板紅色長條）。",
        10, """
        SELECT count(*) FROM inst_enrollments
         WHERE quota_limit IS NOT NULL
           AND used_count + reserved_count >= quota_limit + COALESCE(extended_count,0)"""),
    Cov("quota_extended", "機構方案", "已延長額度",
        "延長是獨立欄位（extended_count），三態恆等式要把它算進去。",
        6, "SELECT count(*) FROM inst_enrollments WHERE COALESCE(extended_count,0) > 0"),

    # ══ 收款與收據 ════════════════════════════════════════════════════
    Cov("pay_unpaid", "收款", "未收款",
        "應收帳冊的主角。徽章 danger 態。",
        80, "SELECT count(*) FROM session_records WHERE payment_status='unpaid' AND NOT is_void"),
    Cov("pay_partial", "收款", "部分收款",
        "徽章的 warn 態。**現在是 0**，那個狀態在整個系統裡從來沒出現過。",
        20, "SELECT count(*) FROM session_records WHERE payment_status='partial'"),
    Cov("pay_discount", "收款", "有優待的場次",
        "優待會讓 amount 與 effective_amount 不同，酬勞要用 commissionable_base 算"
        "（P1 修過：酬勞沒扣 discount_amount）。",
        40, "SELECT count(*) FROM session_records WHERE COALESCE(discount_amount,0) > 0"),
    Cov("pay_void", "收款", "作廢場次",
        "作廢不計入酬勞、不計入核銷（P1 修過：酬勞沒排除作廢）。",
        20, "SELECT count(*) FROM session_records WHERE is_void"),
    Cov("receipt_issued", "收款", "已開立收據",
        "自費需收款案要「收款＋開據」都完成才轉灰。",
        400, "SELECT count(*) FROM receipts WHERE status='issued'"),
    Cov("receipt_voided", "收款", "已作廢收據",
        "P5 的作廢／重印：沿用同一個 base 另開一列，順便有重印軌跡。",
        15, "SELECT count(*) FROM receipts WHERE status='voided'"),

    # ══ 整格轉灰的三條分支（02 §4.3）══════════════════════════════════
    Cov("settle_selfpay_full", "整格轉灰", "自費需收款：收款＋開據都完成",
        "轉灰三條規則之一。",
        200, """
        SELECT count(*) FROM appointments a
          JOIN cases c ON c.id = a.case_id
          JOIN session_records s ON s.appointment_id = a.id AND NOT s.is_void
          JOIN receipts r ON r.session_record_id = s.id AND r.status='issued'
         WHERE a.check_in_status='arrived' AND c.billing_cycle <> 'monthly'
           AND a.plan_id IS NULL AND s.copay_collected_at IS NOT NULL"""),
    Cov("settle_monthly", "整格轉灰", "自費月結：按完已到即轉灰",
        "轉灰三條規則之二。**沒有樣本的話這條寫錯了也不會有人發現**——"
        "第一版就是這樣把月結案判成待處理的。",
        60, """
        SELECT count(*) FROM appointments a JOIN cases c ON c.id = a.case_id
         WHERE a.check_in_status='arrived' AND c.billing_cycle='monthly' AND a.plan_id IS NULL"""),
    Cov("settle_inst_done", "整格轉灰", "機構案：已到＋結清＋提醒全勾",
        "轉灰三條規則之三。",
        80, """
        SELECT count(*) FROM appointments a
         WHERE a.check_in_status='arrived' AND a.plan_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM appointment_admin_tasks t
                            WHERE t.appointment_id = a.id AND NOT t.is_done)"""),
    Cov("settle_inst_blocked", "整格轉灰", "機構案：已到但行政提醒還沒勾完",
        "**閘門擋著的那一側**。只有「全勾」的樣本，等於只驗了通過的分支；"
        "要有沒勾完的才看得出「這格今天還要處理」。",
        30, """
        SELECT count(*) FROM appointments a
         WHERE a.check_in_status='arrived' AND a.plan_id IS NOT NULL
           AND EXISTS (SELECT 1 FROM appointment_admin_tasks t
                        WHERE t.appointment_id = a.id AND NOT t.is_done)"""),
    Cov("admin_tasks_total", "整格轉灰", "行政流程提醒總量",
        "方案清冊說 54 個方案全部都有確認清單，每筆機構場次應有 2–5 項。"
        "現在只有 48 項，等於這個功能在畫面上幾乎不存在。",
        1500, "SELECT count(*) FROM appointment_admin_tasks"),

    # ══ 核銷 ══════════════════════════════════════════════════════════
    Cov("claim_collecting", "核銷", "收集中的核銷案", "容器還在裝。", 5,
        "SELECT count(*) FROM inst_claim_cases WHERE status='collecting' AND voided_at IS NULL"),
    Cov("claim_submitted", "核銷", "已送出等撥款",
        "機構應收的第一段。逾 45 天要標逾期。",
        8, "SELECT count(*) FROM inst_claim_cases WHERE status='submitted' AND voided_at IS NULL"),
    Cov("claim_closed", "核銷", "已結案（款項到帳）", "終態。", 30,
        "SELECT count(*) FROM inst_claim_cases WHERE status='closed'"),
    Cov("claim_voided", "核銷", "已作廢的核銷案", "作廢要能還原裡面的紀錄。", 3,
        "SELECT count(*) FROM inst_claim_cases WHERE voided_at IS NOT NULL"),
    Cov("claim_returned", "核銷", "退回補件",
        "P5 的退回：清掉心理師確認與行政核對兩個閘門、填原因、發通知。"
        "心理師端會標紅底排最上面。",
        15, """
        SELECT count(*) FROM session_records
         WHERE funding_source='institution' AND therapist_doc_submitted_at IS NULL
           AND admin_verified_at IS NULL AND NOT is_void"""),
    Cov("claim_uncollected_stale", "核銷", "跨月遺留的未收納場次",
        "機構應收的第二段「尚未收納」＋跨月提醒。那是**還沒開始要錢**的錢，"
        "07 §4.3 說這是行政最容易漏的一件事。",
        20, f"""
        SELECT count(*) FROM session_records s
         WHERE s.funding_source='institution' AND NOT s.is_void
           AND COALESCE(s.institution_payable,0) > 0
           AND NOT EXISTS (SELECT 1 FROM inst_claim_lines l WHERE l.session_record_id = s.id)
           AND s.session_date < date_trunc('month', (now() {TPE})::date)"""),
    Cov("doc_gate_pending", "核銷", "等心理師確認文件的場次",
        "雙閘門的第一道。心理師端「文件確認」那一頁要有東西。",
        30, """
        SELECT count(*) FROM session_records
         WHERE funding_source='institution' AND therapist_doc_submitted_at IS NULL AND NOT is_void"""),
    Cov("doc_gate_waiting_admin", "核銷", "心理師已確認、等行政核對",
        "雙閘門的第二道。",
        30, """
        SELECT count(*) FROM session_records
         WHERE therapist_doc_submitted_at IS NOT NULL AND admin_verified_at IS NULL AND NOT is_void"""),

    # ══ 酬勞 ══════════════════════════════════════════════════════════
    Cov("payout_pending", "酬勞", "待發放的酬勞單", "月結後、匯款前的狀態。", 8,
        "SELECT count(*) FROM therapist_payouts WHERE status='pending'"),
    Cov("payout_paid", "酬勞", "已發放的酬勞單",
        "已發放是歷史快照，重算不可覆蓋（P1 的冪等要求）。",
        60, "SELECT count(*) FROM therapist_payouts WHERE status='paid'"),
    Cov("payout_outcall_bonus", "酬勞", "外出保底",
        "外展場次的保底加給，酬勞單上是獨立一欄。",
        30, "SELECT count(*) FROM session_records WHERE COALESCE(outcall_bonus,0) > 0"),
    Cov("venue_deduct", "酬勞", "場地費扣回（督導模式 B）",
        "心理師自收督導費、場地費由酬勞回扣。**這個項目曾經完全沒被扣過**"
        "（不是明細沒顯示，是錢根本沒扣）。",
        10, "SELECT count(*) FROM venue_rentals WHERE payer='therapist'"),

    # ══ 場地與雲燈教室 ════════════════════════════════════════════════
    Cov("venue_mode_a", "場地", "督導模式 A（診所收督導費）",
        "模式 A 場地費 $0；模式 B 場地費由酬勞扣回。兩者帳務完全不同。",
        8, "SELECT count(*) FROM venue_rentals WHERE supervision_fee_mode='A'"),
    Cov("venue_mode_b", "場地", "督導模式 B（心理師自收）", "同上。", 8,
        "SELECT count(*) FROM venue_rentals WHERE supervision_fee_mode='B'"),
    Cov("venue_inst_payer", "場地", "機構付款的場地租借",
        "付款方三種：機構／心理師／借用人。未到時付款方要改成借用人。",
        15, "SELECT count(*) FROM venue_rentals WHERE payer='institution'"),
    Cov("hall_executed", "雲燈教室", "已執行的雲燈教室活動",
        "5F 雲燈教室是第三種佔用空間的實體，與診間、場地租借共用衝突檢查。",
        15, "SELECT count(*) FROM hall_bookings WHERE status='executed'"),

    # ══ 媒合 ══════════════════════════════════════════════════════════
    *[
        Cov(f"referral_{st}", "媒合", f"媒合案：{label}",
            "八種狀態的狀態機。每一種都對應媒合列表上不同的操作按鈕。",
            n, f"SELECT count(*) FROM referrals WHERE status='{st}'")
        for st, label, n in [
            ("new", "新增", 5), ("matching", "媒合中", 5), ("unmatched", "不成功／已退回", 5),
            ("accepted", "成功轉預約", 5), ("booked", "初診已預約", 5),
            ("converted", "已轉個案", 10), ("cancelled", "取消媒合", 4), ("closed", "已結案", 4),
        ]
    ],

    # ══ 零星 ══════════════════════════════════════════════════════════
    Cov("notifications", "其他", "通知", "通知中心目前幾乎是空的。", 150,
        "SELECT count(*) FROM notifications"),
    Cov("petty_cash", "其他", "零用金", "財務分頁之一。", 60,
        "SELECT count(*) FROM petty_cash"),
    Cov("product_sales", "其他", "商品販售", "零星帳務。", 40,
        "SELECT count(*) FROM product_sales"),
]


def run(verbose: bool = False) -> int:
    db = SessionLocal()
    failures: list[tuple[Cov, int]] = []
    by_area: dict[str, list[str]] = {}
    try:
        for c in CHECKS:
            try:
                n = db.execute(text(c.sql)).scalar() or 0
            except Exception as e:  # 表還沒建、欄位改名之類
                db.rollback()
                print(f"⚠ [{c.key}] 查詢失敗：{str(e).splitlines()[0][:110]}")
                failures.append((c, -1))
                continue
            ok = n >= c.min_count if c.min_count > 0 else n == 0
            by_area.setdefault(c.area, []).append("✓" if ok else "✗")
            if not ok:
                failures.append((c, n))
            elif verbose:
                print(f"✓ [{c.area}] {c.title:34} {n:>6} ≥ {c.min_count}")
    finally:
        db.close()

    print()
    if failures:
        print(f"未達標的分支（{len(failures)} / {len(CHECKS)}）：\n")
        area = None
        for c, n in failures:
            if c.area != area:
                area = c.area
                print(f"  ── {area}")
            got = "查詢失敗" if n < 0 else (f"{n}（需 {c.min_count}）" if c.min_count else f"{n}（需為 0）")
            print(f"    ✗ {c.title:32} {got}")
            print(f"        {c.why.strip()}")
    # 分區小結：一眼看出哪一塊整體缺得最多
    print("\n分區覆蓋：")
    for a, marks in by_area.items():
        hit = marks.count("✓")
        bar = "█" * round(12 * hit / len(marks)) + "·" * (12 - round(12 * hit / len(marks)))
        print(f"  {a:10} {bar} {hit}/{len(marks)}")

    print()
    if failures:
        print(f"❌ {len(failures)}/{len(CHECKS)} 條分支覆蓋不足")
        return 1
    print(f"✅ {len(CHECKS)} 條分支全部達標")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="檢查假資料是否走過系統的每一條業務分支")
    ap.add_argument("--verbose", "-v", action="store_true", help="達標的也印出來")
    sys.exit(run(verbose=ap.parse_args().verbose))
