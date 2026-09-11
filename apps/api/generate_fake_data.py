"""假資料生成器：把整個診所的一年份營運資料灌進資料庫。

用法：
    DATABASE_URL=postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy \\
        .venv/bin/python generate_fake_data.py --reset

    --reset     先清空所有營運資料（保留 alembic 版本），從零重建
    --seed N    亂數種子，同一個種子產出同一份資料（預設 20260908）
    --months N  往回產生幾個月（預設 12）
    --cases N   個案數（預設 70）
    --no-check  跳過最後的不變量檢查

設計原則（見計畫書 D3）——依「有沒有跨表不變量」決定走哪個通道：

    參考資料（使用者/診間/機構/合約/方案/費率）  → ORM 直寫
    預約、報到、未到、取消、額度轉移             → **呼叫既有 service 函式**
    歷史帳冊、收據、酬勞、核銷                   → ORM 直寫
    HTTP API                                     → 完全不用（被過去日期防呆擋住）

第二列是關鍵：額度三態恆等式只活在 app/institution/adapter.py 裡，生成器
自己重寫一份保證會跟本尊漂移。所以預約一律走 create_appointment()、報到一律
走 perform_check_in()，讓 quote/reserve/consume 全部照真實流程跑一遍。
代價是慢（每筆十幾個查詢），換來的是「這份資料跟系統自己長出來的一模一樣」。

時間回填：perform_check_in() 有一個 keyword-only 的 now 參數（不在 HTTP 端點
簽名上，所以外部偽造不了），生成器傳入那場諮商當時的時間。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy")

from psycopg2.extras import DateTimeTZRange  # noqa: E402
from sqlalchemy import func, text  # noqa: E402

from app.auth.password import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.funding import registry as funding_registry  # noqa: E402
from app.funding.dto import QuoteRequest  # noqa: E402
from app.funding.registry import get_provider as get_funding_provider  # noqa: E402
from app.institution.adapter import InstitutionFundingProvider  # noqa: E402
from app.institution.models.claim_case import InstClaimCase  # noqa: E402
from app.institution.models.claim_line import InstClaimLine  # noqa: E402
from app.institution.models.enrollment import InstEnrollment  # noqa: E402
from app.institution.models.plan import InstPlan  # noqa: E402
from app.institution.seed_plans import reset_plans, seed_plans  # noqa: E402
from app.models.appointment import Appointment  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.claim_batch import ClaimBatch  # noqa: E402
from app.models.couple_member import CoupleMember  # noqa: E402
from app.models.fee_item import FeeItem  # noqa: E402
from app.models.institution import Institution  # noqa: E402
from app.models.petty_cash import PettyCash  # noqa: E402
from app.models.product_sales import ProductSale  # noqa: E402
from app.models.receipt import Receipt  # noqa: E402
from app.models.room import Room  # noqa: E402
from app.models.session_record import SessionRecord  # noqa: E402
from app.models.therapist_payout import PayoutDetail, TherapistPayout  # noqa: E402
from app.models.user import User  # noqa: E402
from app.referral.models.batch import ReferralBatch, ReferralBatchMember  # noqa: E402
from app.referral.models.referral import Referral  # noqa: E402
from app.routers.appointments import create_appointment, perform_check_in  # noqa: E402
from app.routers.payouts import payout_line_amount  # noqa: E402
from app.schemas.appointment import AppointmentCreate, CheckInRequest  # noqa: E402
from app.services import numbering  # noqa: E402
from app.utils.encryption import encrypt_national_id, hmac_national_id  # noqa: E402
from app.utils.tz import TAIPEI, to_local_date  # noqa: E402
from scripts import fake_people as fp  # noqa: E402

from seed import FINAL_ROOM_ROSTER  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────
# 資料集組成矩陣（計畫書 D4）
#
# 每一種「方案原型」都要有個案掛在上面，否則對應的畫面邏輯永遠沒有資料可看：
# 分級計價、次數池、金額池、per_case_count 容器、回扣制、therapist_rate、
# 諮商型態計價、登記時數轉換。
# ─────────────────────────────────────────────────────────────────────────

# (方案名稱, 個案數, 說明) —— 方案名稱要跟 seed_plans.py 的 InstPlan.name 完全一致
INSTITUTION_MIX = [
    ("衛生局市民", 5, "visit_seq 分級計價：第1次$1600全額補助、第2次起自付$200"),
    ("15-45青壯", 6, "合約層級次數池（378 次/年）"),
    ("國軍-個別", 5, "合約層級金額池（$149,000/年）+ 需個案代號"),
    ("市政府人事處", 4, "核銷容器 per_case_count=4"),
    ("教支中心", 3, "回饋制：心理師自收、回繳診所（酬勞是扣項）"),
    ("聊心茶室", 3, "price_source=therapist_rate，依心理師鐘點費"),
    ("家防中心", 3, "諮商型態計價：個別$1400 / 家族$2000"),
    ("南家扶", 2, "諮商型態計價 + 需評估"),
    ("台南地院", 3, "登記時數轉換（1 實際小時 → 登記 2 小時 @$800）"),
    ("脆弱家庭", 2, "核銷容器 per_case_count=8"),
    # compensation_mode="none"：借場地沒有心理師勞務，酬勞單上是「不計酬場次」
    # 那一區。這個方案原本是 11 個裡唯一零使用的，所以那一區永遠不會出現。
    ("鉅微/借場地", 2, "不計酬（compensation_mode=none）"),
]
SELF_PAY_MIX = [("once", 16), ("monthly", 9), ("multiple", 5)]
COUPLE_CASES = 6
#: 機構合療伴侶案。07 的重要設計：機構核銷以人為單位，伴侶案沒有真人身分
#: 不能當核銷對象，所以合療預約要選付款方。原本一筆都沒有，那個分流在畫面上
#: 完全看不到。
COUPLE_INSTITUTION_CASES = 3

# 生命週期分佈（在上面的付款分類之上疊加）
LIFECYCLE = {
    "closed": 18,        # 已結案（療程自然告一段落的多半會走到這裡）
    "reopened": 3,       # 結案後又復案
    "churn_risk": 7,     # ≥45 天沒有預約，仍未結案（流失預警）
    "quota_exhausted": 6,
    "extended": 4,       # 額度延長過（家防中心「6+3」那種）
    # 兩段式編號的第一段：已建檔、還沒補身分證、還沒有病歷號。原本一筆都沒有，
    # 於是「暫存 → 轉正式 → 產生病歷號」整條流程在畫面上看不到。
    "initial": 4,
}

BUSINESS_HOURS = list(range(8, 21))   # 08:00–21:00 起始，最晚 21:00–22:00 結束
SESSION_MINUTES = 60
COUPLE_MINUTES = 90


class Generator:
    def __init__(self, db, rng: random.Random, today: date, months: int, n_cases: int, scale: int = 1):
        self.db = db
        self.rng = rng
        self.today = today
        self.scale = scale
        self.start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
        self.n_cases = n_cases
        # 佔用表：避免撞到 excl_room_time_overlap，也避免心理師同時段被排兩場。
        # 事先擋掉比等資料庫丟 IntegrityError 再重試快得多。
        self.room_busy: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
        self.therapist_busy: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
        self.stats: dict[str, int] = defaultdict(int)
        self.start_tz = TAIPEI

    # ── 工具 ──────────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        print(f"  {msg}", flush=True)

    def _overlaps(self, busy: list[tuple[datetime, datetime]], s: datetime, e: datetime) -> bool:
        return any(s < be and e > bs for bs, be in busy)

    def _slot(self, day: date, minutes: int) -> tuple[datetime, datetime] | None:
        """在營業時段裡挑一個起訖（台北時間，回傳 aware datetime）。"""
        hour = self.rng.choice(BUSINESS_HOURS)
        minute = self.rng.choice([0, 0, 0, 30])  # 多數整點起
        start = datetime.combine(day, time(hour, minute), tzinfo=TAIPEI)
        end = start + timedelta(minutes=minutes)
        if end.hour > 22 or (end.hour == 22 and end.minute > 0):
            return None
        return start, end

    def find_slot(self, day: date, therapist_id: int, minutes: int, need_room: bool):
        """找一個診間與心理師都有空的時段。試 12 次找不到就放棄這一天。"""
        for _ in range(12):
            got = self._slot(day, minutes)
            if not got:
                continue
            start, end = got
            if self._overlaps(self.therapist_busy[therapist_id], start, end):
                continue
            if not need_room:
                return start, end, None
            rooms = self.rooms[:]
            self.rng.shuffle(rooms)
            for room in rooms:
                if not self._overlaps(self.room_busy[room.id], start, end):
                    return start, end, room
        return None

    def occupy(self, therapist_id: int, room_id: int | None, start: datetime, end: datetime) -> None:
        self.therapist_busy[therapist_id].append((start, end))
        if room_id:
            self.room_busy[room_id].append((start, end))

    # ── 1. 參考資料 ────────────────────────────────────────────────────

    def reference_data(self) -> None:
        print("\n[1/7] 參考資料：使用者、診間、機構合約與方案")
        db = self.db

        self.admin = self._user("admin@cheerpsy.com", "管理員", "admin", None)
        self.staff = self._user("staff@cheerpsy.com", "櫃台行政", "staff", "S001")
        self._user("accountant@cheerpsy.com", "會計", "accountant", "C001")

        names = ["呂孟育", "林紀宇", "林容蒂", "邱似齡", "蔡孟潔", "陳慧苓", "游子瑩",
                 "葉邦彥", "鄭幼毅", "楊顯欽", "劉柏宏", "邱惟雅", "潘柔靜", "邱意祺",
                 "劉彥君", "羅紀萱", "黃慧婷"]
        self.therapists = []
        for i, name in enumerate(names, start=1):
            # 抽成率刻意不一致：0.65～0.75，讓酬勞報表看得出個別差異
            rate = Decimal(str(self.rng.choice([0.65, 0.70, 0.70, 0.70, 0.72, 0.75])))
            t = self._user(f"therapist{i}@cheerpsy.com", name, "therapist", f"T{i:03d}",
                           commission_rate=rate, base_price=Decimal(self.rng.choice([1600, 1800, 2000])))
            self.therapists.append(t)
        # 前 12 位是「在職主力」，其餘偶爾接案 —— 讓接案量報表有高低差
        self.active_therapists = self.therapists[:12]
        db.flush()

        self.rooms = db.query(Room).order_by(Room.id).all()
        if not self.rooms:
            for code, floor, use_type, size in FINAL_ROOM_ROSTER:
                db.add(Room(name=code, floor=floor, room_code=code, use_type=use_type, size=size))
            db.flush()
            self.rooms = db.query(Room).order_by(Room.id).all()

        if not db.query(FeeItem).first():
            for i, nm in enumerate(["心理諮商", "心理治療", "專業評估", "會談", "人際互動治療",
                                    "摘要報告", "會面交往", "工作坊"], start=1):
                db.add(FeeItem(name=nm, is_default=(nm == "心理治療"), is_active=True, sort_order=i))
            db.flush()

        seed_plans(db=self.db, force=True)
        self.plans = {p.name: p for p in db.query(InstPlan).all()}
        db.commit()
        self.log(f"心理師 {len(self.therapists)} 位、診間 {len(self.rooms)} 間、方案 {len(self.plans)} 個")

    def _user(self, email, name, role, code, **kw) -> User:
        u = self.db.query(User).filter(User.email == email).first()
        if u:
            return u
        u = User(email=email, password_hash=hash_password("admin123"), name=name,
                 role=role, user_code=code, is_active=True, **kw)
        self.db.add(u)
        self.db.flush()
        return u

    # ── 2. 個案 ────────────────────────────────────────────────────────

    def build_cases(self) -> None:
        print("\n[2/7] 個案：自費 / 機構各原型 / 伴侶案")
        db = self.db
        self.cases: list[dict] = []

        # 個案的初診日平均分佈在整個期間，但前段多一些（才有足夠長的歷程）
        span = (self.today - self.start).days

        k = self.scale
        for cycle, n in SELF_PAY_MIX:
            for _ in range(n * k):
                self._make_case(funding="self_pay", billing_cycle=cycle, span=span)

        for plan_name, n, _desc in INSTITUTION_MIX:
            plan = self.plans.get(plan_name)
            if plan is None:
                self.log(f"⚠ 找不到方案「{plan_name}」，略過")
                continue
            for _ in range(n * k):
                self._make_case(funding="institution", billing_cycle="once", span=span, plan=plan)

        self._make_couples()
        self._assign_outreach_cases()
        self._assign_online_cases()
        self._assign_consult_types()
        db.commit()

        by_kind = defaultdict(int)
        for c in self.cases:
            by_kind[c["kind"]] += 1
        self.log(f"共 {len(self.cases)} 案：" + "、".join(f"{k} {v}" for k, v in sorted(by_kind.items())))

    def _make_case(self, funding: str, billing_cycle: str, span: int, plan: InstPlan | None = None) -> dict:
        db = self.db
        p = fp.person(self.rng)
        # 初診日在整個期間內平均分佈。原本用三角分佈往中後段集中，結果最早的
        # 幾個月幾乎沒有新案、當月更是掛零——進案統計預設看當月，一打開就是
        # 「共 0 案」，看起來像壞掉。實際診所的每月進案本來就大致平均。
        intake = self.start + timedelta(days=self.rng.randint(0, span))
        # 進案統計是以「第一次場次落在哪個月」計算的（reports.py:_intake_data），
        # 而畫面預設看當月。當月只過了幾天，平均分佈只會分到一兩案，一打開就是
        # 「共 0 案」。刻意保證幾個個案的初診落在最近一週，讓預設畫面有東西看。
        if self.stats["intake_recent"] < 5 and self.rng.random() < 0.12:
            intake = self.today - timedelta(days=self.rng.randint(2, 7))
            self.stats["intake_recent"] += 1
        therapist = self.rng.choice(self.active_therapists)
        birth = date(self.rng.randint(1960, 2010), self.rng.randint(1, 12), self.rng.randint(1, 28))

        case = Case(
            name=p["name"], gender=p["gender"], phone=p["phone"], phone_home=p["phone_home"],
            address=p["address"], birth_date=birth, age=intake.year - birth.year,
            emergency_contact=p["emergency_contact"], emergency_phone=p["emergency_phone"],
            initial_visit_date=intake, funding_source=funding,
            institution_id=plan.contract.institution_id if plan else None,
            therapist_id=therapist.id, billing_cycle=billing_cycle,
            referral_source=self.rng.choice(fp.SOURCES),
            is_designated=self.rng.random() < 0.25,
            status="ongoing", created_by=self.admin.id,
        )
        case.national_id_encrypted = encrypt_national_id(p["national_id"])
        case.national_id_hmac = hmac_national_id(p["national_id"])
        # 兩段式編號：初診有到才產生病歷號，日期用初診日（不是灌資料當天）
        case.case_number = numbering.next_case_number(
            db, on_date=intake, national_id_last2=p["national_id"][-2:]
        )
        db.add(case)
        db.flush()

        entry = {
            "case": case, "therapist": therapist, "intake": intake, "plan": plan,
            "kind": plan.name if plan else f"自費-{billing_cycle}",
            "funding": funding, "billing_cycle": billing_cycle,
            "modality": self._case_modality(therapist, plan),
        }
        if plan is not None:
            get_funding_provider().enroll(
                db, case_id=case.id, plan_id=plan.id, created_by=self.admin.id,
                external_case_code=(f"EXT{self.rng.randint(10000, 99999)}"
                                    if plan.requires_external_code else None),
            )
            # 需評估的方案（南家扶）：一半還在等評估結果，一半已通過
            if plan.requires_assessment:
                e = db.query(InstEnrollment).filter(
                    InstEnrollment.case_id == case.id, InstEnrollment.plan_id == plan.id
                ).first()
                e.assessment_status = "approved" if self.rng.random() < 0.7 else "pending"
            db.flush()
        self.cases.append(entry)
        return entry

    def _make_couples(self) -> None:
        """伴侶案：自己是一列 cases（收費單位），兩位成員各自仍是獨立個案。"""
        db = self.db
        span = (self.today - self.start).days
        # 機構合療排在前面幾筆：機構核銷以人為單位，伴侶案沒有真人身分不能當
        # 核銷對象，所以合療預約要選付款方（07 的設計）。原本一筆都沒有。
        inst_plan = self.plans.get("家防中心")
        total = (COUPLE_CASES + COUPLE_INSTITUTION_CASES) * self.scale
        n_inst = COUPLE_INSTITUTION_CASES * self.scale if inst_plan else 0
        for i in range(total):
            as_institution = i < n_inst
            members = []
            therapist = self.rng.choice(self.active_therapists)
            intake = self.start + timedelta(days=int(self.rng.triangular(0, span, span * 0.6)))
            for _ in range(2):
                # 機構合療：成員各自掛在機構方案上（核銷對象是成員本人）
                m = (self._make_case(funding="institution", billing_cycle="once", span=span, plan=inst_plan)
                     if as_institution
                     else self._make_case(funding="self_pay", billing_cycle="once", span=span))
                m["case"].therapist_id = therapist.id  # 伴侶的共同心理師
                m["kind"] = "伴侶成員"
                members.append(m["case"])
            couple = Case(
                name=f"{members[0].name}＆{members[1].name}（伴侶）",
                case_type="couple", status="ongoing",
                funding_source="institution" if as_institution else "self_pay",
                therapist_id=therapist.id, billing_cycle="once",
                initial_visit_date=intake,
                case_number=numbering.next_couple_number(db, on_date=intake),
                created_by=self.admin.id,
            )
            db.add(couple)
            db.flush()
            for m in members:
                db.add(CoupleMember(couple_case_id=couple.id, member_case_id=m.id))
            db.flush()
            self.cases.append({
                "case": couple, "therapist": therapist, "intake": intake, "plan": None,
                "kind": "機構伴侶案" if as_institution else "伴侶案",
                "funding": "institution" if as_institution else "self_pay",
                "billing_cycle": "once", "modality": "in_person",
                "couple_members": members,
            })

    # ── 3. 預約與報到 ──────────────────────────────────────────────────

    def build_appointments(self) -> None:
        print("\n[3/7] 預約與報到（走真實 service，額度全程照規則轉移）")
        for idx, entry in enumerate(self.cases, start=1):
            self._sessions_for_case(entry)
            if idx % 15 == 0:
                self.db.commit()
                self.log(f"…{idx}/{len(self.cases)} 案，已建立 {self.stats['appointments']} 筆預約")
        self.db.commit()
        self.log(
            f"預約 {self.stats['appointments']} 筆："
            f"已到 {self.stats['arrived']}、未到 {self.stats['no_show']}、"
            f"取消 {self.stats['cancelled']}、未來待報到 {self.stats['pending']}"
        )

    def _sessions_for_case(self, entry: dict) -> None:
        case: Case = entry["case"]
        therapist: User = entry["therapist"]
        plan: InstPlan | None = entry["plan"]
        is_couple = case.case_type == "couple"
        minutes = COUPLE_MINUTES if is_couple else SESSION_MINUTES

        interval = self.rng.choice([7, 7, 7, 14, 14, 21])
        day = entry["intake"]
        # 流失預警案：最後一次預約要在 45 天以前
        # 治療關係什麼時候結束，決定了這個案在畫面上長什麼樣子。與其先決定
        # 「談幾次」再算日期（起始早的個案會在半年前就談完，整份資料看起來
        # 一半的人都流失了），不如先決定「談到什麼時候」，次數自然浮現。
        r = self.rng.random()
        if r < 0.62:
            ending = "active"      # 仍在進行，最後一次就在最近
            cutoff = self.today + timedelta(days=22)
        elif r < 0.77:
            ending = "churn"       # 悄悄不來了 → 流失預警
            cutoff = self.today - timedelta(days=self.rng.randint(35, 110))
        else:
            ending = "completed"   # 自然告一段落，之後多半會被結案
            cutoff = day + timedelta(days=self.rng.randint(100, 260))
            cutoff = min(cutoff, self.today - timedelta(days=20))
        entry["ending"] = ending
        self.stats[f"ending_{ending}"] += 1

        # 上限只是防呆，不是主要控制項。設太低會反咬：每週一次、談滿一年的
        # 個案會在中途被截斷，最後一次預約落在好幾個月前，儀表板就把它算成
        # 流失預警——明明是「還在談」的個案。
        target = min(60, max(1, (cutoff - day).days // interval + 1))

        for _ in range(target):
            if day > cutoff:
                break
            # 避開週日；週六只排上午
            if day.weekday() == 6:
                day += timedelta(days=1)

            slot = self.find_slot(day, therapist.id, minutes, need_room=True)
            day += timedelta(days=interval)
            if slot is None:
                continue
            start, end, room = slot

            session_type, location_kind = self._pick_modality(entry)
            consult_type = "couple" if is_couple else self._pick_consult_type(entry)
            room_id = room.id if session_type == "in_person" else None
            if session_type != "in_person":
                room = None

            appt = self._create_one(entry, therapist, room_id, start, end,
                                    session_type, consult_type, location_kind)
            if appt is None:
                continue
            self.occupy(therapist.id, room_id, start, end)
            self.stats["appointments"] += 1
            self._resolve_attendance(appt, entry, start)

    def _case_modality(self, therapist: User, plan: InstPlan | None) -> str:
        """這個個案主要用哪一種型式。

        外展**不是隨機撒的**：診所裡只有少數幾位心理師接外展的機構案，
        跟著機構走。所以先挑出「外展心理師」與「外展機構」，兩者都對上
        才有可能是外展個案——這樣資料看起來才像真的分工，而不是每個人
        每種型式都做一點。
        """
        # 外展與視訊都不在這裡決定——見 _assign_outreach_cases / _assign_online_cases。
        # 原本是層層擲骰（方案對 ∧ 心理師對 ∧ 55%），三個條件連乘之後 scale=1
        # 實測產出 0 筆外展，於是外展的四種型態組合、外出保底、外展計額度
        # 全部沒有樣本。**綁定要用挑的，不是用擲的。**
        # 視訊不在這裡擲骰——見 build_cases 末尾的 _assign_online_cases()。
        # 「每週 3–5 次」是一個**總量**，用每案 3.5% 的機率去湊，在個案數少的
        # 時候會整個擲空（scale=1 實測擲出 0 個，於是視訊連結、待轉發提醒
        # 那一整條全部消失）。總量要用算的，不是用擲的。
        return "in_person"

    def _assign_outreach_cases(self) -> None:
        """外展個案：先挑出「外展心理師 × 外展機構」，再從交集裡指定。

        外展**不是隨機撒的**（你的說法：綁在某幾位心理師接的某些機構上）。
        但「綁定」要用挑的不是用擲的——三個條件連乘的機率版本實測產出 0 筆。

        外展不佔診間、金流與一般場次相同，所以量少沒關係；重點是每種諮商型態
        都要有樣本，否則那幾格的費率規則寫錯了驗不出來。
        """
        actives = self.active_therapists
        self._outreach_therapists = {t.id for t in self.rng.sample(actives, min(3, len(actives)))}
        self._outreach_plans = {"家防中心", "脆弱家庭", "南家扶", "市政府人事處"}

        eligible = [
            c for c in self.cases
            if c["case"].case_type != "couple"
            and c["plan"] is not None and c["plan"].name in self._outreach_plans
        ]
        # 先取「心理師也對得上」的，不夠再從同方案的其他案補（機構不變、
        # 改成另一位心理師接，這在真實診所也會發生）
        matched = [c for c in eligible if c["therapist"].id in self._outreach_therapists]
        rest = [c for c in eligible if c not in matched]
        self.rng.shuffle(rest)
        n = max(8, 3 * self.scale)
        chosen = (matched + rest)[:n]
        for c in chosen:
            c["modality"] = "outdoor"
        self.log(f"外展個案 {len(chosen)} 案（{len(self._outreach_therapists)} 位心理師 × "
                 f"{len(self._outreach_plans)} 個機構）")

    def _assign_online_cases(self) -> None:
        """視訊個案：由「每週幾次」回推張數，再指定給個案。

        診所的實際規模是**整間每週 3–5 次視訊**（不是每天都有）。一個視訊
        個案在期間內大約談 `weeks/interval` 次，所以需要的個案數＝
        目標總場次 ÷ 每案場次。
        """
        weeks = max(1, (self.today - self.start).days // 7)
        target_sessions = int(weeks * 4)          # 每週 4 次（3–5 的中位）
        per_case = 12                             # 一個視訊個案平均談幾次
        n = max(2, round(target_sessions / per_case))
        pool = [c for c in self.cases
                if c["case"].case_type != "couple" and c.get("modality") == "in_person"]
        for entry in self.rng.sample(pool, min(n, len(pool))):
            entry["modality"] = "online"
        self.log(f"視訊個案 {min(n, len(pool))} 案（目標每週 4 次、期間 {weeks} 週）")

    def _pick_modality(self, entry: dict) -> tuple[str, str]:
        """型式由**個案**決定，不是逐筆擲骰。

        原本每一筆預約各自擲骰（82% 現場 / 12% 視訊 / 6% 外展），結果是每個
        個案的療程東跳西跳：這次現場、下次視訊、再下次外展。真實的樣子是
        **一個個案通常固定一種型式**，而且——

          · 視訊是補充，整間診所每週 3–5 次，不是每天都有
          · 外展綁在「某幾位心理師接的某些機構」上，跟著機構走，不是隨機撒

        所以型式在建個案時就定下來（entry["modality"]），這裡只負責把它
        翻成 (session_type, location_kind)，並留一點點偶發的例外。
        """
        m = entry.get("modality", "in_person")
        if m == "outdoor":
            # 外展個案偶爾也會回所內談
            if self.rng.random() < 0.15:
                return "in_person", "clinic"
            return "outdoor", self.rng.choice(["home", "onsite", "offsite"])
        if m == "online":
            if self.rng.random() < 0.2:
                return "in_person", "clinic"
            return "online", "clinic"
        return "in_person", "clinic"

    def _pick_consult_type(self, entry: dict) -> str:
        """諮商型態也是**個案層級**的屬性，不是逐筆擲骰。

        一個來談親職議題的個案不會這次親職、下次家族。原本只有家防中心與
        南家扶兩個方案會變化，其餘一律個別，結果是費率規則的第二條計價軸
        幾乎沒有樣本——而那正是南家扶／家防中心曾經永遠報價 $0 的地方。

        更麻煩的是交叉組合：視訊與外展本來量就少，再乘上型態就更稀疏。
        所以型態在建個案時就配好（見 _assign_consult_types），這裡只讀。
        """
        return entry.get("consult_type", "individual")

    def _assign_consult_types(self) -> None:
        """把諮商型態配到個案上，並**刻意確保每個「型式 × 型態」組合都有樣本**。

        放著讓機率去撒的話，視訊 × 家族、外展 × 親職這種格子會只有兩三筆——
        費率規則在那些格子上寫錯了也驗不出來。所以先每個組合硬塞一批，
        剩下的才按分佈隨機配。
        """
        NON_INDIVIDUAL = ["family", "parenting", "couple"]
        by_modality: dict[str, list[dict]] = {"in_person": [], "online": [], "outdoor": []}
        for c in self.cases:
            if c["case"].case_type == "couple":
                c["consult_type"] = "couple"
                continue
            c["consult_type"] = "individual"
            by_modality.setdefault(c.get("modality", "in_person"), []).append(c)

        # 每個組合至少配到 quota 個案（覆蓋率檢查門檻是每格 12 筆預約，
        # 一個個案通常談十幾次，所以 2 個案就夠撐起一格）
        quota = max(2, self.scale // 3)
        for modality, pool in by_modality.items():
            self.rng.shuffle(pool)
            i = 0
            for ct in NON_INDIVIDUAL:
                for entry in pool[i:i + quota]:
                    entry["consult_type"] = ct
                i += quota
            # 剩下的個案：少數仍是非個別，其餘個別
            for entry in pool[i:]:
                if self.rng.random() < 0.12:
                    entry["consult_type"] = self.rng.choice(NON_INDIVIDUAL)
        self.log("諮商型態已配到個案（每個「型式 × 型態」組合都保證有樣本）")

    def _create_one(self, entry, therapist, room_id, start, end,
                    session_type, consult_type, location_kind) -> Appointment | None:
        """走真實的 create_appointment()，額度 quote/reserve 全部照跑。"""
        case: Case = entry["case"]
        plan: InstPlan | None = entry["plan"]
        body = AppointmentCreate(
            case_id=case.id, room_id=room_id, session_type=session_type,
            consult_type=consult_type, location_kind=location_kind,
            start_time=start.astimezone(tz=None), end_time=end.astimezone(tz=None),
            plan_id=plan.id if plan else None,
            amount=None if plan else float(self._self_pay_price(entry)),
            funding_source="institution" if plan else "self_pay",
        )
        # 先把前一筆的收款/開據落地。create_appointment() 失敗時會 rollback 整個
        # session，連帶把上一筆 _settle() 只 flush 沒 commit 的修改一起丟掉——
        # 機構個案額度用罄後每一筆都會走到那條路，等於整段收款紀錄憑空消失。
        self.db.commit()
        try:
            resp = create_appointment(body, self.admin, self.db)
        except Exception as exc:
            self.db.rollback()
            detail = str(getattr(exc, "detail", None) or type(exc).__name__)
            # 額度用罄 → 回落自費。這正是 v7「個案管理」定案的結帳方式推算規則：
            # 「額度用罄或方案過期 → 自動回落到個案的自費設定」。所以機構個案
            # 用完額度之後還是會繼續談，只是改成自費——資料集要長成這樣才對，
            # 不然「機構案用完額度後怎麼辦」這條路徑永遠沒有資料可看。
            if plan is not None and "用罄" in detail:
                self.stats["fallback_to_self_pay"] += 1
                body = body.model_copy(update={
                    "plan_id": None, "funding_source": "self_pay",
                    "amount": float(self._self_pay_price(entry)),
                })
                try:
                    resp = create_appointment(body, self.admin, self.db)
                except Exception as exc2:
                    self.db.rollback()
                    self.stats["skip: " + str(getattr(exc2, "detail", exc2))[:20]] += 1
                    return None
            else:
                self.stats["skip: " + detail[:20]] += 1
                return None
        return self.db.query(Appointment).filter(Appointment.id == resp.id).first()

    def _self_pay_price(self, entry) -> int:
        if entry["case"].case_type == "couple":
            return 3000
        return int(entry["therapist"].base_price or 1800)

    def _resolve_attendance(self, appt: Appointment, entry: dict, start: datetime) -> None:
        """過去的預約要有結果；未來的維持待報到。"""
        if start.date() > self.today:
            self.stats["pending"] += 1
            return

        r = self.rng.random()
        # 88% 到、6% 未到、6% 取消 —— 取消要在場次開始之前處理掉
        if r < 0.06:
            appt.status = "cancelled"
            if appt.plan_id:
                get_funding_provider().release(self.db, appt.id, reason="cancelled",
                                               bill_no_show_fee=False)
            self.db.flush()
            self.stats["cancelled"] += 1
            return

        if r < 0.12:
            perform_check_in(
                self.db, appt.id,
                CheckInRequest(status="no_show", no_show_reason=self.rng.choice(fp.NO_SHOW_REASONS)),
                self.staff, now=start + timedelta(minutes=20),
            )
            self.stats["no_show"] += 1
            return

        perform_check_in(self.db, appt.id, CheckInRequest(status="arrived"),
                         self.staff, now=start + timedelta(minutes=2))
        self.stats["arrived"] += 1
        self._settle(appt, start)

    # ── 4. 收款與收據 ──────────────────────────────────────────────────

    def _settle(self, appt: Appointment, start: datetime) -> None:
        """報到後的收款與開據。歷史帳直接寫 ORM（見 D3 第三列），
        因為 payment_step()/issue_receipt() 的時間戳硬綁 now()。"""
        db = self.db
        sr = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
        if sr is None:
            return
        sr.consult_type = appt.consult_type
        sr.location_kind = appt.location_kind

        payable = sr.case_payable if sr.case_payable is not None else Decimal(str(sr.amount))
        r = self.rng.random()

        # 優待減免：少數個案有
        if r < 0.03 and payable > 0:
            sr.discount_amount = Decimal(self.rng.choice([100, 200, 300]))
            sr.discount_note = self.rng.choice(["低收入戶減免", "學生優待", "續談優惠"])
            payable -= sr.discount_amount

        # 作廢：極少數（誤登）
        if r > 0.99:
            sr.is_void = True
            sr.void_reason = "誤登，實際未進行"
            sr.voided_at = start + timedelta(days=1)
            sr.voided_by = self.admin.id
            if sr.plan_id:
                get_funding_provider().unconsume(db, appt.id)
            db.flush()
            self.stats["voided"] += 1
            return

        month_cutoff = self.today - timedelta(days=5)
        if sr.funding_source == "self_pay":
            # 月結案在月底才收；次結當場收
            unpaid = (appt.case.billing_cycle == "monthly" and start.date() > month_cutoff.replace(day=1)) \
                or self.rng.random() < 0.07
            if not unpaid:
                self._collect(sr, payable, start)
        else:
            # 機構案只收個案自付額，機構那份走核銷
            if payable > 0 and self.rng.random() < 0.93:
                self._collect(sr, payable, start)
        db.flush()

    def _collect(self, sr: SessionRecord, payable: Decimal, start: datetime) -> None:
        # 部分收款：個案付了一部分。徽章的 warn 態只有這裡會產生，原本全站 0 筆，
        # 等於那個狀態從來沒在畫面上出現過。
        if payable > 0 and self.rng.random() < 0.03:
            sr.payment_status = "partial"
            sr.copay_collected_at = start + timedelta(minutes=65)
            sr.copay_payment_method = "cash"
            sr.copay_payment_note = f"先付 {int(payable) // 2}，餘額下次補"
            self.stats["partial"] += 1
            return

        method = "cash" if self.rng.random() < 0.7 else "transfer"
        sr.copay_collected_at = start + timedelta(minutes=65)
        sr.copay_payment_method = method
        sr.copay_payment_note = f"末五碼 {self.rng.randint(10000, 99999)}" if method == "transfer" else None
        # 純自費案的 payment_status 跟著收款走（機構案要等核銷）
        if sr.institution_payable is None or sr.institution_payable == 0:
            sr.payment_status = "paid"
            sr.paid_at = sr.copay_collected_at
            sr.payment_method = method
            sr.payment_note = sr.copay_payment_note
        self.stats["collected"] += 1

        if payable > 0 and self.rng.random() < 0.88:
            self._issue_receipt(sr, payable, start)

    def _issue_receipt(self, sr: SessionRecord, amount: Decimal, start: datetime) -> None:
        db = self.db
        item = db.query(FeeItem).filter(FeeItem.is_default.is_(True)).first() \
            or db.query(FeeItem).first()
        no = numbering.next_receipt_no(db, on_date=sr.session_date)
        rec = Receipt(receipt_no=no, session_record_id=sr.id, amount=amount,
                      fee_item_id=item.id if item else None, status="issued",
                      created_by=self.staff.id, created_at=sr.copay_collected_at)
        db.add(rec)
        db.flush()
        self.stats["receipts"] += 1

        r = self.rng.random()
        if r < 0.03:
            # 作廢後重開：原號 -3，另開一張新的
            rec.status = "voided"
            rec.void_reason = self.rng.choice(["金額打錯", "開錯抬頭", "個案要求改開公司抬頭"])
            rec.voided_at = start + timedelta(days=self.rng.randint(1, 5))
            rec.voided_by = self.staff.id
            rec.receipt_no = numbering.receipt_variant(no, numbering.RECEIPT_STATE_VOID)
            db.add(Receipt(
                receipt_no=numbering.next_receipt_no(db, on_date=sr.session_date),
                session_record_id=sr.id, amount=amount,
                fee_item_id=item.id if item else None, status="issued",
                created_by=self.staff.id, created_at=rec.voided_at,
            ))
            self.stats["receipt_voided"] += 1
        elif r < 0.05:
            # 重印：同一個 base，尾碼 -2，原件仍有效
            db.add(Receipt(
                receipt_no=numbering.receipt_variant(no, numbering.RECEIPT_STATE_REPRINT),
                session_record_id=sr.id, amount=amount,
                fee_item_id=item.id if item else None, status="issued",
                note="個案遺失，補印",
                created_by=self.staff.id, created_at=start + timedelta(days=self.rng.randint(2, 30)),
            ))
            self.stats["receipt_reprint"] += 1
        db.flush()

    # ── 5. 生命週期收尾（結案 / 復案 / 額度延長）────────────────────────

    def apply_lifecycle(self) -> None:
        print("\n[4/7] 生命週期：結案、復案、額度延長")
        db = self.db
        pool = [c for c in self.cases if c["case"].case_type != "couple"]
        self.rng.shuffle(pool)

        with_plan = [c for c in pool if c["plan"] is not None]
        for entry in with_plan[:(LIFECYCLE["extended"] * self.scale)]:
            e = db.query(InstEnrollment).filter(
                InstEnrollment.case_id == entry["case"].id).first()
            if e:
                get_funding_provider().extend_enrollment(
                    db, e.id, additional_count=3, note="個案狀況需延長，主管已核准",
                    approved_by=self.admin.id)
                self.stats["extended"] += 1

        # 優先結案「療程自然告一段落」的那批。否則它們會一直掛在 ongoing、
        # 最後一次預約又在幾個月前，儀表板會把它們全部算成流失預警——
        # 真實的診所是談完就結案，不是放著不管。
        pool.sort(key=lambda c: 0 if c.get("ending") == "completed" else 1)
        closed = 0
        for entry in pool:
            if closed >= (LIFECYCLE["closed"] * self.scale):
                break
            case = entry["case"]
            if case.status != "ongoing":
                continue
            last = db.query(Appointment).filter(Appointment.case_id == case.id) \
                .order_by(Appointment.id.desc()).first()
            if last is None:
                continue
            closed_at = (last.time_range.upper + timedelta(days=self.rng.randint(7, 40)))
            if to_local_date(closed_at) >= self.today:
                continue
            self._close_case(case, closed_at)
            closed += 1

        # 復案：從剛結案的裡面挑幾個
        reopened = [c for c in pool if c["case"].status == "closed"][:(LIFECYCLE["reopened"] * self.scale)]
        for entry in reopened:
            case = entry["case"]
            case.status = "ongoing"
            case.reopened_at = case.closed_at + timedelta(days=self.rng.randint(30, 120))
            case.reopened_by = self.admin.id
            self.stats["reopened"] += 1
        # ── 暫存案（尚未轉正式）────────────────────────────────────────
        # 兩段式編號的第一段：已建檔、還沒補身分證、還沒有病歷號。
        # **刻意挑還沒有任何預約的個案**——已經談過的人不可能還停在暫存。
        # 這些個案在畫面上撐起「暫存 → 補個資 → 產生病歷號」那條流程，
        # 也是初診報到唯一能被 demo 到的地方。
        untouched = [
            c for c in pool
            if c["case"].status == "ongoing"
            and not db.query(Appointment).filter(Appointment.case_id == c["case"].id).first()
        ]
        for entry in untouched[:(LIFECYCLE["initial"] * self.scale)]:
            case = entry["case"]
            case.status = "initial"
            case.case_number = None
            case.national_id_encrypted = None
            case.national_id_hmac = None
            # temp_seq 沒有 numbering 函式，cases.py:134 是直接 max+1
            case.temp_seq = (db.query(func.coalesce(func.max(Case.temp_seq), 0)).scalar() or 0) + 1
            self.stats["initial"] += 1

        db.commit()
        self.log(f"結案 {closed}、復案 {self.stats['reopened']}、額度延長 {self.stats['extended']}"
                 f"、暫存案 {self.stats['initial']}")

    def _close_case(self, case: Case, closed_at: datetime) -> None:
        db = self.db
        db.query(Appointment).filter(
            Appointment.case_id == case.id, Appointment.status == "booked",
            text("lower(time_range) > :t").bindparams(t=closed_at),
        ).update({Appointment.status: "cancelled"}, synchronize_session=False)
        # 結案要一起關機構方案（P1 修好的那條路），否則額度被永久佔住
        get_funding_provider().close_case_enrollments(db, case.id)
        case.status = "closed"
        case.closed_at = closed_at
        case.closed_by = self.admin.id
        case.closure_reason = self.rng.choice(fp.CLOSURE_REASONS)
        db.flush()
        self.stats["closed"] += 1


def truncate_all(db) -> None:
    """清空所有營運資料。alembic_version 與 number_sequences 一起清掉——
    配號計數器留著會讓下一輪從舊號碼接續，資料看起來就不像從頭長出來的。"""
    tables = [
        "payout_details", "therapist_payouts", "inst_claim_lines", "inst_claim_cases",
        "receipts", "session_records", "appointments", "inst_enrollments",
        "referral_batch_members", "referral_batches", "referrals",
        "couple_members", "case_institution_quotas", "cases",
        "inst_rate_rules", "inst_plans", "inst_quota_pools", "inst_contracts",
        "claim_batches", "invoices", "product_sales", "petty_cash",
        "reminder_log", "notifications", "audit_log", "invitations",
        "quota_templates", "fee_items", "rooms", "institutions", "users",
        "number_sequences",
    ]
    db.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    db.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description="產生一整套符合業務規則的假資料")
    ap.add_argument("--reset", action="store_true", help="先清空所有營運資料")
    ap.add_argument("--seed", type=int, default=20260908, help="亂數種子（同種子＝同資料）")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--cases", type=int, default=70)
    # 密度是這份資料集能不能展示價值的關鍵（13 §2.1）：診間日曆一天只有幾筆
    # 的話，所有為密度做的設計——四行結構、整格轉灰、最後一次標黃、跨格
    # rowSpan——在一片空白上完全看不出在解決什麼問題。
    # scale 直接乘在組成矩陣上；開發時用 1 跑得快，展示與壓測用大的。
    ap.add_argument("--scale", type=int, default=1,
                    help="組成矩陣的倍率。1=快速開發用；12 約當平日每天 50–60 場現場")
    ap.add_argument("--no-check", action="store_true", help="跳過不變量檢查")
    args = ap.parse_args()

    # 這支腳本不經過 app.main，所以要自己把機構合約子系統接上——否則
    # enroll()/quote()/reserve() 全部會撞 NullProvider 的 LookupError。
    funding_registry.register(InstitutionFundingProvider())

    db = SessionLocal()
    rng = random.Random(args.seed)
    today = date.today()

    try:
        if args.reset:
            print("清空既有資料…")
            truncate_all(db)

        gen = Generator(db, rng, today, args.months, args.cases, scale=max(1, args.scale))
        print(f"期間 {gen.start} ~ {today}（{args.months} 個月），種子 {args.seed}")
        gen.reference_data()
        gen.build_cases()
        gen.build_appointments()
        gen.apply_lifecycle()
        return gen_finish(gen, db, args)
    finally:
        db.close()


def gen_finish(gen: "Generator", db, args) -> int:
    from scripts import fake_data_finance as fin

    # 順序有意義：加時會改場次金額，核銷申請金額與心理師酬勞都是從場次
    # 金額算出來的，所以 P4 那批一定要先跑完，否則兩邊會對不起來。
    fin.build_scheduling_extras(gen)
    fin.build_claims(gen)
    fin.build_payouts(gen)
    fin.build_referrals(gen)
    fin.build_misc(gen)
    reset_sequences(db)

    print("\n完成。統計：")
    for k, v in sorted(gen.stats.items()):
        print(f"  {k:24} {v}")

    if args.no_check:
        return 0
    print("\n[7/7] 不變量檢查")
    from scripts.check_invariants import run as run_checks
    return run_checks(verbose=True)


def reset_sequences(db) -> None:
    """依 資料庫結構與資料轉換規範 §5.4：大量匯入後要把序列推到最大 id，
    否則之後從畫面新增資料會撞主鍵。"""
    for table in ("users", "institutions", "rooms", "cases", "appointments",
                  "session_records", "receipts", "claim_batches", "therapist_payouts",
                  "referrals", "inst_contracts", "inst_plans", "inst_enrollments",
                  "inst_claim_cases"):
        db.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
        ))
    db.execute(text(
        "SELECT setval('cases_temp_seq_seq', COALESCE((SELECT MAX(temp_seq) FROM cases), 1))"
    ))
    db.commit()


if __name__ == "__main__":
    sys.exit(main())
