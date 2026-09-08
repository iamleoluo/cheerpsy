"""假資料生成器的後半段：核銷、酬勞、媒合、零星帳務。

拆成獨立模組純粹是為了讓 generate_fake_data.py 不要變成一千五百行。
所有函式都吃同一個 Generator 實例（gen），共用它的 db / rng / stats。

這一段幾乎全部是 ORM 直寫而不是呼叫 service，原因見計畫書 D3 第三列：
核銷與酬勞的 service 函式時間戳都綁 now()，而這裡要產生的是「去年十月那批
已經入帳的核銷案」。額度與報價那類有跨表不變量的東西，在前半段就已經
透過真實 service 跑完了，這裡不再碰。
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from psycopg2.extras import DateTimeTZRange
from sqlalchemy import text

from app.institution.claims import service as claims_service
from app.institution.models.claim_case import InstClaimCase
from app.institution.models.claim_line import InstClaimLine
from app.institution.models.plan import InstPlan
from app.models.appointment import Appointment
from app.models.case import Case
from app.models.claim_batch import ClaimBatch
from app.models.institution import Institution
from app.models.petty_cash import PettyCash
from app.models.product_sales import ProductSale
from app.models.session_record import SessionRecord
from app.models.therapist_payout import PayoutDetail, TherapistPayout
from app.models.user import User
from app.referral.models.batch import ReferralBatch, ReferralBatchMember
from app.referral.models.referral import Referral
from app.routers.payouts import payout_line_amount
from app.services import numbering
from scripts import fake_people as fp


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _month_bounds(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


# ─────────────────────────────────────────────────────────────────────────
# 核銷：機構走新的 inst_claim_cases 容器，自費走舊的 claim_batches
# （09 §1.4 定案：依付款方切開，兩套機制並存）
# ─────────────────────────────────────────────────────────────────────────

def build_claims(gen) -> None:
    print("\n[5/7] 核銷：機構容器 + 自費批次")
    _institution_claims(gen)
    _self_pay_batches(gen)
    gen.db.commit()
    gen.log(
        f"機構核銷案 {gen.stats['claim_cases']} 件（含 {gen.stats['claim_void']} 件作廢）、"
        f"自費批次 {gen.stats['claim_batches']} 件、未收納 {gen.stats['uncollected']} 筆"
    )


def _institution_claims(gen) -> None:
    db, rng = gen.db, gen.rng
    # 依「核銷群組 × 月份」分組——同一個機構的不同方案要分開建案（v7 規則）
    groups: dict[str, list[SessionRecord]] = defaultdict(list)
    rows = (
        db.query(SessionRecord, InstPlan)
        .join(InstPlan, InstPlan.id == SessionRecord.plan_id)
        .filter(SessionRecord.is_void.is_(False))
        .all()
    )
    for sr, plan in rows:
        if plan.compensation_mode == "none":
            continue  # 借場地沒有核銷
        groups[plan.claim_group_key or plan.name].append(sr)

    # 最後一個月刻意留著不收納，讓「跨月遺留提醒」有東西可提醒
    leave_uncollected_from = gen.today.replace(day=1)

    for group_key, records in groups.items():
        by_month: dict[tuple[int, int], list[SessionRecord]] = defaultdict(list)
        for sr in records:
            by_month[(sr.session_date.year, sr.session_date.month)].append(sr)

        months = sorted(by_month)
        for i, (y, m) in enumerate(months):
            recs = by_month[(y, m)]
            p_start, p_end = _month_bounds(y, m)
            if p_start >= leave_uncollected_from:
                gen.stats["uncollected"] += len(recs)
                continue

            # 刻意在其中一個群組製造一段期間缺口與一次重疊，讓 P5 的
            # 「缺口/重疊警告」有真實資料可以顯示（v7 規則：警告不阻擋）
            if group_key == "衛生局市民" and i == 2:
                gen.stats["uncollected"] += len(recs)
                gen.stats["deliberate_gap"] += 1
                continue
            if group_key == "國軍" and i == 3:
                p_start = p_start - timedelta(days=7)  # 與上一期重疊 7 天
                gen.stats["deliberate_overlap"] += 1

            _one_claim_case(gen, group_key, recs, p_start, p_end, y, m)


def _one_claim_case(gen, group_key, recs, p_start, p_end, y, m) -> None:
    db, rng = gen.db, gen.rng
    age_days = (gen.today - p_end).days

    cc = InstClaimCase(
        claim_no=numbering.next_claim_no(db, on_date=p_start),
        claim_group_key=group_key,
        grouping_mode="period",
        period_start=p_start, period_end=p_end,
        status="collecting", settlement_mode="claim_then_pay",
        created_by=gen.admin.id,
        created_at=datetime.combine(p_end, datetime.min.time()),
    )
    db.add(cc)
    db.flush()

    # 走真正的 attach_records()，這樣登記時數轉換（台南地院 1hr→2hr@$800）
    # 與個案代號檢查都會照規則跑一遍——生成器自己塞 InstClaimLine 的話，
    # 那兩條規則在資料上就永遠看不到效果。
    lines = claims_service.attach_records(
        db, cc.id, [sr.id for sr in recs], enforce_external_code=False,
    )
    total = sum((ln.claimed_amount or Decimal("0")) for ln in lines)

    for sr in recs:
        # 文件雙閘門：心理師提交 + 行政核對
        if rng.random() < 0.9:
            sr.therapist_doc_submitted_at = datetime.combine(p_end, datetime.min.time())
            sr.therapist_doc_submitted_by = sr.therapist_id
            if rng.random() < 0.95:
                sr.admin_verified_at = sr.therapist_doc_submitted_at + timedelta(days=1)
                sr.admin_verified_by = gen.admin.id
        # 少數被行政退回補件：兩個閘門都清掉，並留下通知
        elif rng.random() < 0.35:
            claims_service.return_for_correction(
                db, sr.id,
                rng.choice(["出席單缺個案簽名", "服務紀錄表日期填錯", "缺個案同意書影本",
                            "時數與出席單對不上"]),
                gen.admin.id,
            )
            gen.stats["returned_for_correction"] += 1
    db.flush()
    gen.stats["claim_cases"] += 1

    # 狀態依「這期距今多久」推進：愈舊的愈可能已經入帳
    r = rng.random()
    if age_days > 120 and r < 0.06:
        # 作廢：紀錄脫離本案、付款狀態退回未核銷
        db.query(InstClaimLine).filter(InstClaimLine.claim_case_id == cc.id).delete()
        for sr in recs:
            sr.payment_status = "unpaid"
        cc.status = "void"
        cc.voided_at = datetime.combine(p_end + timedelta(days=20), datetime.min.time())
        cc.voided_reason = rng.choice(["重複建案", "期間切錯", "機構要求重送"])
        gen.stats["claim_void"] += 1
        db.flush()
        return

    if age_days < 25:
        return  # 還在收集中

    cc.status = "submitted"
    cc.applied_amount = total
    submitted = datetime.combine(p_end + timedelta(days=rng.randint(3, 15)), datetime.min.time())
    for sr in recs:
        sr.payment_status = "claiming"
    gen.stats["claim_submitted"] += 1

    if age_days < 60:
        db.flush()
        return

    # 已撥款：機構通常會扣二代健保補充保費與匯費
    received = total * Decimal("0.98")
    cc.status = "closed"
    cc.received_date = (submitted + timedelta(days=rng.randint(20, 50))).date()
    cc.received_amount = received.quantize(Decimal("0.01"))
    cc.income_tax_amount = (total * Decimal("0.02")).quantize(Decimal("0.01"))
    cc.transfer_fee = Decimal("30")
    cc.net_received = (cc.received_amount - cc.income_tax_amount - cc.transfer_fee).quantize(Decimal("0.01"))
    cc.locked_at = datetime.combine(cc.received_date, datetime.min.time())
    for sr in recs:
        sr.payment_status = "claimed"
    gen.stats["claim_closed"] += 1
    db.flush()


def _self_pay_batches(gen) -> None:
    """月結個案的自費批次（09 §7.1：舊 claim_batches 留給自費用）。"""
    db, rng = gen.db, gen.rng
    monthly_cases = [c for c in gen.cases if c["billing_cycle"] == "monthly"]
    for entry in monthly_cases:
        case = entry["case"]
        recs = (
            db.query(SessionRecord)
            .filter(SessionRecord.case_id == case.id,
                    SessionRecord.funding_source == "self_pay",
                    SessionRecord.is_void.is_(False),
                    SessionRecord.claim_batch_id.is_(None))
            .all()
        )
        by_month = defaultdict(list)
        for sr in recs:
            by_month[(sr.session_date.year, sr.session_date.month)].append(sr)

        for (y, m), group in sorted(by_month.items()):
            p_start, p_end = _month_bounds(y, m)
            if p_end >= gen.today:
                continue
            batch = ClaimBatch(
                batch_number=numbering.next_batch_suffix(
                    db, base=f"SM-{case.case_number}-{y}{m:02d}"),
                type="self_pay", billing_cycle="monthly", case_id=case.id,
                period_start=p_start, period_end=p_end,
                total_amount=sum(float(s.amount) for s in group),
                status="collecting",
                created_by=gen.admin.id,
                created_at=datetime.combine(p_end, datetime.min.time()),
            )
            db.add(batch)
            db.flush()
            for sr in group:
                sr.claim_batch_id = batch.id
            # 上個月的還在收，更早的都收到錢了
            if (gen.today - p_end).days > 35:
                batch.status = "received"
                batch.received_at = datetime.combine(p_end + timedelta(days=rng.randint(5, 25)),
                                                     datetime.min.time())
                for sr in group:
                    if sr.payment_status == "unpaid":
                        sr.payment_status = "paid"
                        sr.paid_at = batch.received_at
                        sr.payment_method = "transfer"
            gen.stats["claim_batches"] += 1
    db.flush()


# ─────────────────────────────────────────────────────────────────────────
# 心理師酬勞
# ─────────────────────────────────────────────────────────────────────────

def build_payouts(gen) -> None:
    print("\n[6/7] 心理師月酬勞")
    db = gen.db
    for (y, m) in _months_between(gen.start, gen.today):
        p_start, p_end = _month_bounds(y, m)
        if p_start > gen.today:
            continue
        rows = (
            db.query(SessionRecord)
            .filter(SessionRecord.session_date >= p_start,
                    SessionRecord.session_date <= p_end,
                    SessionRecord.is_void.is_(False))
            .all()
        )
        by_t = defaultdict(list)
        for sr in rows:
            by_t[sr.therapist_id].append(sr)

        for tid, recs in by_t.items():
            total = sum(payout_line_amount(sr) for sr in recs)
            payout = TherapistPayout(
                therapist_id=tid, payout_month=f"{y}-{m:02d}",
                total_amount=float(total), status="pending", created_by=gen.admin.id,
            )
            # 上上個月以前都發過了；最近兩個月還在待發
            if (gen.today - p_end).days > 40:
                payout.status = "paid"
                payout.paid_at = datetime.combine(p_end + timedelta(days=10), datetime.min.time())
                gen.stats["payout_paid"] += 1
            else:
                gen.stats["payout_pending"] += 1
            db.add(payout)
            db.flush()
            for sr in recs:
                db.add(PayoutDetail(payout_id=payout.id, session_id=sr.id))
    db.commit()
    gen.log(f"已發放 {gen.stats['payout_paid']} 筆、待發 {gen.stats['payout_pending']} 筆")



# ─────────────────────────────────────────────────────────────────────────
# 媒合：八種狀態各要有資料，否則媒合列表的每個分頁都是空的
# ─────────────────────────────────────────────────────────────────────────

REFERRAL_PLAN = [
    ("new", 5), ("matching", 5), ("unmatched", 5), ("accepted", 5),
    ("booked", 4), ("converted", 8), ("cancelled", 4), ("closed", 4),
]
DECLINE_REASONS = ["unavailable", "not_specialty", "dual_relationship", "other"]


def build_referrals(gen) -> None:
    print("\n[7/7] 媒合案（八種狀態）")
    db, rng = gen.db, gen.rng
    span = (gen.today - gen.start).days

    for status, n in REFERRAL_PLAN:
        for _ in range(n):
            p = fp.person(rng)
            created = gen.today - timedelta(days=rng.randint(2, min(span, 200)))
            designated = rng.choice(gen.active_therapists) if rng.random() < 0.3 else None
            ref = Referral(
                referral_code=numbering.next_referral_code(db, on_date=created),
                name=p["name"], gender=p["gender"], phone=p["phone"],
                age=rng.randint(16, 65),
                mode=rng.choice(["in_person", "in_person", "in_person", "online"]),
                issues=__import__("json").dumps(rng.sample(fp.ISSUES, rng.randint(1, 3)),
                                                ensure_ascii=False),
                issue_note=rng.choice(["近三個月睡眠變差、工作無法專注", "與家人衝突頻繁",
                                       "希望處理長期低落情緒", ""]) or None,
                designated_therapist_id=designated.id if designated else None,
                source=rng.choice(fp.SOURCES),
                availability=rng.choice(["週二下午、週四晚上", "平日晚上皆可",
                                         "週末上午", "週三全天"]),
                status=status, created_by=gen.staff.id,
                created_at=datetime.combine(created, datetime.min.time()),
            )
            db.add(ref)
            db.flush()
            _referral_history(gen, ref, status, created)
            gen.stats[f"referral_{status}"] += 1
    db.commit()
    gen.log(f"媒合案 {sum(n for _, n in REFERRAL_PLAN)} 件，八種狀態齊備")


def _referral_history(gen, ref: Referral, status: str, created: date) -> None:
    """依最終狀態倒推該有的派案批次與回覆紀錄。"""
    db, rng = gen.db, gen.rng
    if status == "new":
        return

    sent = datetime.combine(created + timedelta(days=1), datetime.min.time())
    invited = rng.sample(gen.active_therapists, rng.randint(1, 3))
    batch = ReferralBatch(referral_id=ref.id, batch_seq=1, is_open=True,
                          sent_at=sent, created_by=gen.staff.id)
    db.add(batch)
    db.flush()
    members = [ReferralBatchMember(batch_id=batch.id, therapist_id=t.id) for t in invited]
    db.add_all(members)
    db.flush()

    if status == "matching":
        return  # 等待回覆中

    if status == "unmatched":
        # 全部婉拒，或逾時未回覆（RETURN_DAYS=3）
        if rng.random() < 0.6:
            for m in members:
                m.reply_status = "declined"
                m.decline_reason = rng.choice(DECLINE_REASONS)
                m.replied_at = sent + timedelta(days=1)
        else:
            for m in members:
                m.reply_status = "expired"
                m.replied_at = sent + timedelta(days=3)
        batch.is_open = False
        db.flush()
        return

    # 以下都是「有人承接」：第一位承接，其餘轉 superseded
    acceptor = members[0]
    slots = [(datetime.combine(created + timedelta(days=d), datetime.min.time())
              .replace(hour=rng.choice([10, 14, 19])).isoformat())
             for d in rng.sample(range(5, 20), rng.randint(1, 3))]
    acceptor.reply_status = "accepted"
    acceptor.proposed_slots = __import__("json").dumps(slots)
    acceptor.replied_at = sent + timedelta(days=1)
    for m in members[1:]:
        m.reply_status = "superseded"
        m.replied_at = acceptor.replied_at
    batch.is_open = False
    ref.accepted_therapist_id = acceptor.therapist_id
    db.flush()

    if status in ("accepted",):
        return

    if status == "cancelled":
        ref.close_reason = rng.choice(["個案自行取消", "個案聯繫不上", "個案改至他所"])
        ref.closed_at = datetime.combine(created + timedelta(days=rng.randint(3, 20)),
                                         datetime.min.time())
        return
    if status == "closed":
        ref.close_reason = "初診未到，多次聯繫未果"
        ref.closed_at = datetime.combine(created + timedelta(days=rng.randint(10, 40)),
                                         datetime.min.time())
        return

    # booked / converted：接上一個真實個案，代表媒合真的產出了初診預約
    linked = _link_referral_to_case(gen, ref, acceptor.therapist_id)
    if linked and status == "converted":
        ref.closed_at = datetime.combine(created + timedelta(days=rng.randint(7, 30)),
                                         datetime.min.time())


def _link_referral_to_case(gen, ref: Referral, therapist_id: int) -> bool:
    """把媒合案接到一個真實個案上（兩碼並存以利追溯，v7 編號規則）。"""
    db = gen.db
    if not getattr(gen, "_unlinked_cases", None):
        gen._unlinked_cases = [
            c["case"] for c in gen.cases
            if c["case"].case_type != "couple" and c["case"].therapist_id == therapist_id
        ] or [c["case"] for c in gen.cases if c["case"].case_type != "couple"]
    if not gen._unlinked_cases:
        return False
    case = gen._unlinked_cases.pop()
    first_appt = (
        db.query(Appointment).filter(Appointment.case_id == case.id)
        .order_by(Appointment.id.asc()).first()
    )
    ref.converted_case_id = case.id
    ref.appointment_id = first_appt.id if first_appt else None
    ref.name = case.name
    ref.phone = case.phone
    db.flush()
    return True


# ─────────────────────────────────────────────────────────────────────────
# 零星帳務：商品販售、零用金
# ─────────────────────────────────────────────────────────────────────────

PRODUCTS = [("情緒卡牌", 1200), ("療癒繪本", 480), ("沙遊玩具組", 3500),
            ("正念練習手冊", 350), ("親職教養手冊", 420)]
PETTY = [("cleaning", "清潔用品", 300, 1500), ("supplies", "文具耗材", 200, 2000),
         ("electricity", "電費", 3000, 9000), ("water", "水費", 400, 1200),
         ("other", "雜支", 100, 800)]


def build_misc(gen) -> None:
    db, rng = gen.db, gen.rng
    span = (gen.today - gen.start).days

    for _ in range(60):
        d = gen.start + timedelta(days=rng.randint(0, span))
        name, price = rng.choice(PRODUCTS)
        qty = rng.randint(1, 2)
        db.add(ProductSale(
            sale_date=d, product_name=name, amount=price * qty, quantity=qty,
            payment_method=rng.choice(["cash", "cash", "transfer"]),
            receipt_no=numbering.next_product_receipt_no(db, on_date=d),
            created_by=gen.staff.id,
        ))
    db.flush()

    # 零用金：balance_after 是累計餘額，必須依序算好（資料庫規範 §5.5 第 3 點）。
    # 支出之外一定要有撥補，否則餘額一路往負的走，儀表板會一直喊「餘額不足」。
    rows = []
    for _ in range(90):
        d = gen.start + timedelta(days=rng.randint(0, span))
        cat, item, lo, hi = rng.choice(PETTY)
        rows.append((d, cat, item, Decimal(-rng.randint(lo, hi))))
    for (y, m) in _months_between(gen.start, gen.today):      # 每月初撥補
        rows.append((date(y, m, 1), "other", "零用金撥補", Decimal(15000)))

    balance = Decimal("20000")
    for d, cat, item, amount in sorted(rows, key=lambda r: r[0]):
        balance += amount
        db.add(PettyCash(date=d, amount=amount, category=cat, description=item,
                         balance_after=balance, created_by=gen.staff.id))
    db.commit()
    gen.stats["product_sales"] = 60
    gen.stats["petty_cash"] = len(rows)


# ─────────────────────────────────────────────────────────────────────────
# P4 新排程實體：場地租借、5F 雲燈教室、加時、視訊連結、請假、行政提醒
# ─────────────────────────────────────────────────────────────────────────

VENDORS = [
    ("蛹之生心理諮商所", "institution"),
    ("鉅微管理顧問股份有限公司", "institution"),
    ("EAPC 員工協助中心", "institution"),
]
HALL_EVENTS = [
    "親職教養講座", "正念減壓工作坊", "職場心理健康講座", "青少年情緒管理團體",
    "照顧者支持團體", "心理師繼續教育課程", "家長成長團體",
]


def build_scheduling_extras(gen) -> None:
    """P4 那批實體的假資料。跑在預約之後——場地租借要跟一般預約搶診間，
    衝突表得先被填滿才測得出真實的排擠。"""
    print("\n[8/9] 場地租借、雲燈教室、加時、視訊、請假、行政提醒")
    _venue_rentals(gen)
    _hall_bookings(gen)
    _duration_adjustments(gen)
    _video_links(gen)
    _leaves(gen)
    _tick_admin_tasks(gen)
    gen.db.commit()
    gen.log(
        f"場地租借 {gen.stats['venue_rentals']} 筆、雲燈教室 {gen.stats['hall_bookings']} 場、"
        f"加時 {gen.stats['duration_adjusted']} 筆、視訊連結 {gen.stats['video_links']} 筆、"
        f"請假 {gen.stats['leaves']} 筆、行政提醒已勾 {gen.stats['tasks_done']}/{gen.stats['tasks_total']}"
    )


def _venue_rentals(gen) -> None:
    from app.models.venue_rental import VenueRental
    from app.services import room_occupancy

    db, rng = gen.db, gen.rng
    span = (gen.today - gen.start).days
    made = 0
    for _ in range(140):                      # 試 140 次，撞到已佔用就跳過
        if made >= 60:
            break
        d = gen.start + timedelta(days=rng.randint(0, span + 20))
        if d.weekday() == 6:
            continue
        slot = gen.find_slot(d, therapist_id=-1, minutes=rng.choice([120, 180]), need_room=True)
        if slot is None:
            continue
        start, end, room = slot
        if room_occupancy.find_conflicts(db, room.id, start, end):
            continue

        is_supervision = rng.random() < 0.45
        if is_supervision:
            mode = rng.choice(["A", "B"])
            therapist = rng.choice(gen.active_therapists)
            kind, renter_name, inst_id = "private", therapist.name, None
            therapist_id = therapist.id
            amount = Decimal("0") if mode == "A" else Decimal(rng.choice([800, 1200]))
            payer = "renter" if mode == "A" else "therapist"
            purpose = "個別督導" if rng.random() < 0.6 else "團體督導"
        else:
            mode, therapist_id = None, None
            renter_name, kind = rng.choice(VENDORS)
            inst = db.query(Institution).filter(Institution.name == renter_name).first()
            inst_id = inst.id if inst else None
            amount = Decimal(rng.choice([1000, 1200, 1500, 2000]))
            payer = "institution"
            purpose = rng.choice(["團體諮商", "工作坊", "會議", "教育訓練"])

        rental = VenueRental(
            rental_no=numbering.next_venue_rental_no(db, on_date=start.date()),
            room_id=room.id, time_range=DateTimeTZRange(start, end),
            purpose=purpose, renter_kind=kind, renter_name=renter_name,
            institution_id=inst_id, renter_therapist_id=therapist_id,
            supervision_fee_mode=mode, amount=amount, payer=payer,
            created_by=gen.staff.id,
        )
        # 過去的要有出席結果；未到時付款方改為借用人自付
        if start.date() <= gen.today:
            if rng.random() < 0.1:
                rental.attendance = "no_show"
                rental.payer = "renter"
            else:
                rental.attendance = "arrived"
            rental.attended_at = start + timedelta(minutes=5)
            rental.attended_by = gen.staff.id
        db.add(rental)
        db.flush()
        gen.occupy(-1, room.id, start, end)
        made += 1
    gen.stats["venue_rentals"] = made


def _hall_bookings(gen) -> None:
    from app.models.hall_booking import HallBooking

    db, rng = gen.db, gen.rng
    span = (gen.today - gen.start).days
    used_days: set[date] = set()
    made = 0
    for _ in range(90):
        if made >= 36:
            break
        d = gen.start + timedelta(days=rng.randint(0, span + 25))
        if d in used_days or d.weekday() == 6:
            continue
        used_days.add(d)
        ev_start = datetime.combine(d, datetime.min.time(),
                                    tzinfo=gen.start_tz).replace(hour=rng.choice([9, 13, 18]))
        ev_end = ev_start + timedelta(hours=rng.choice([2, 3]))

        internal = rng.random() < 0.56
        lecturer = rng.choice(gen.active_therapists) if internal else None
        h = HallBooking(
            title=rng.choice(HALL_EVENTS),
            setup_range=DateTimeTZRange(ev_start - timedelta(hours=1), ev_start),
            event_range=DateTimeTZRange(ev_start, ev_end),
            lecturer_kind="internal" if internal else "external",
            lecturer_therapist_id=lecturer.id if lecturer else None,
            lecturer_name=None if internal else rng.choice(
                ["王志明 講師", "李美華 講師", "張建良 教授", "陳怡君 心理師"]),
            lecturer_fee=Decimal(rng.choice([3000, 4500, 6000, 8000])),
            # 外聘講師常由主辦單位直接付款，不進診所帳
            fee_to_clinic_account=internal or rng.random() < 0.35,
            borrower=rng.choice(["臺南市政府社會局", "臺南市政府衛生局", "所內活動",
                                 "教育部_教師諮商輔導支持中心", "自辦推廣"]),
            attendee_count=rng.randint(12, 60),
            created_by=gen.staff.id,
        )
        if ev_start.date() <= gen.today:
            h.status = "cancelled" if rng.random() < 0.17 else "executed"
        db.add(h)
        db.flush()
        made += 1
    gen.stats["hall_bookings"] = made


def _duration_adjustments(gen) -> None:
    """加時／縮短：改寫實際起訖與金額。這裡直接寫 ORM 而不是打端點，因為
    端點會擋「已收款」，而歷史資料絕大多數都已經收過款了。"""
    db, rng = gen.db, gen.rng
    rows = (
        db.query(SessionRecord, Appointment)
        .join(Appointment, Appointment.id == SessionRecord.appointment_id)
        .filter(SessionRecord.is_void.is_(False))
        .all()
    )
    rng.shuffle(rows)
    for sr, appt in rows[:60]:
        if not appt.time_range or not appt.time_range.lower:
            continue
        lower, upper = appt.time_range.lower, appt.time_range.upper
        old_min = max(1, int((upper - lower).total_seconds() // 60))
        delta = rng.choice([-15, 15, 30, 30])          # 多數是延長
        new_min = old_min + delta
        if new_min < 30:
            continue
        # 只縮短或在自己的時段內延長會撞到鄰場，所以加時一律往後延，
        # 且先確認沒撞到——撞到就跳過，跟真實流程一樣（01 §C1 不擠掉別人）
        new_end = lower + timedelta(minutes=new_min)
        if delta > 0 and appt.room_id:
            from app.services import room_occupancy
            if room_occupancy.find_conflicts(db, appt.room_id, lower, new_end,
                                             exclude_appointment_id=appt.id):
                continue
        unit_per_min = Decimal(str(appt.amount)) / Decimal(old_min)
        appt.actual_start, appt.actual_end = lower, new_end
        appt.duration_adjusted_at = upper
        appt.duration_adjusted_by = gen.staff.id
        appt.duration_note = rng.choice([
            "個案情緒未穩，延長會談", "個案提前結束", "危機處理，延長 30 分鐘",
            "家長臨時加入，延長"])
        appt.time_range = DateTimeTZRange(lower, new_end)
        appt.amount = (unit_per_min * Decimal(new_min)).quantize(Decimal("1"))
        # 與 adjust_duration 端點同一套切分規則：自付額固定，差額歸機構
        if appt.institution_payable is not None:
            case_part = Decimal(str(appt.case_payable or 0))
            appt.institution_payable = max(Decimal("0"), Decimal(str(appt.amount)) - case_part)
            sr.institution_payable = appt.institution_payable
        if appt.commissionable_base is not None:
            base_per_min = Decimal(str(appt.commissionable_base)) / Decimal(old_min)
            appt.commissionable_base = (base_per_min * Decimal(new_min)).quantize(Decimal("0.01"))
            sr.commissionable_base = appt.commissionable_base
        sr.amount = appt.amount
        gen.stats["duration_adjusted"] += 1
    db.flush()



def _video_links(gen) -> None:
    db, rng = gen.db, gen.rng
    rows = db.query(Appointment).filter(Appointment.session_type == "online").all()
    for appt in rows:
        if rng.random() < 0.15:
            continue                                  # 有些心理師還沒貼
        appt.video_link = f"https://meet.cheerpsy.tw/{rng.randint(100000, 999999)}"
        # 未來的預約有一部分還沒轉發 → 行政端的「待轉發」待辦才有東西
        if appt.time_range and appt.time_range.lower.date() <= gen.today or rng.random() < 0.7:
            appt.video_forwarded_at = appt.time_range.lower - timedelta(days=1)
            appt.video_forwarded_by = gen.staff.id
        gen.stats["video_links"] += 1
    db.flush()


def _leaves(gen) -> None:
    """把一部分已取消的預約標記成「個案請假」——請假在資料上就是帶原因的取消。"""
    db, rng = gen.db, gen.rng
    rows = (
        db.query(Appointment)
        .filter(Appointment.status == "cancelled", Appointment.leave_reason.is_(None))
        .all()
    )
    rng.shuffle(rows)
    for appt in rows[: max(1, len(rows) // 3)]:
        appt.leave_reason = rng.choice([
            "個案臨時出差", "個案生病", "家中臨時有事", "工作無法排開", ""]) or None
        appt.leave_at = appt.time_range.lower - timedelta(days=rng.randint(1, 3))
        appt.leave_by = appt.therapist_id
        gen.stats["leaves"] += 1
    db.flush()


def _tick_admin_tasks(gen) -> None:
    """行政流程提醒：多數已勾（含執行人與時間），少數留著沒勾——
    診間日曆的「整格轉灰」判斷才有東西可判。"""
    from app.models.appointment_admin_task import AppointmentAdminTask

    db, rng = gen.db, gen.rng
    tasks = (
        db.query(AppointmentAdminTask, Appointment)
        .join(Appointment, Appointment.id == AppointmentAdminTask.appointment_id)
        .all()
    )
    names = {t.id: t.name for t in gen.therapists}
    for task, appt in tasks:
        gen.stats["tasks_total"] += 1
        past = appt.time_range and appt.time_range.lower.date() <= gen.today
        if not past or rng.random() > 0.85:
            continue
        task.is_done = True
        task.done_at = appt.time_range.lower + timedelta(minutes=rng.randint(-30, 90))
        if task.side == "therapist":
            task.done_by = appt.therapist_id
            task.done_by_name = names.get(appt.therapist_id)
        else:
            task.done_by = gen.staff.id
            task.done_by_name = gen.staff.name
        gen.stats["tasks_done"] += 1
    db.flush()
