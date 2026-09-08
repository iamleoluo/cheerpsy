"""全系統識別碼配號。06 P0 排定要做、一直沒做的那一支（見 08 §6 第一項缺口）。

取代散落各處的 `COUNT(*) + 1`。舊寫法有三個問題：

  ① 併發不安全——兩個請求同時數到 N，都配 N+1，其中一個撞 unique。
  ② 刪一列就會重發已經用過的號碼。
  ③ 全部綁死 `datetime.now()`，導致「補一筆去年的紀錄」拿到今年的號碼。

改用一張 `number_sequences(scope, last_seq)` 表，配號是單一原子語句：

    UPDATE number_sequences SET last_seq = last_seq + 1
     WHERE scope = :scope RETURNING last_seq

Postgres 會把該列鎖到交易結束，第二個交易排隊等待，所以不會發出重複號碼；
交易 rollback 時號碼跟著還回去，不會留下空號。scope 字串本身帶日期
（`receipt:20260908:C`），所以配「哪一天的號」純粹由呼叫端傳入的 `on_date`
決定——這正是灌 12 個月歷史假資料需要的能力。

每支函式一律 keyword-only 的 `on_date`，模組內不出現 `date.today()`。

**首次使用某個 scope 時**會從既有資料回填（取已存在號碼的最大流水號），
所以掛到既有資料庫上不會從 1 重來。回填只做一次，之後這張表就是唯一真相。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

# 收據分類碼：C=諮商相關、O=其他（商品、場地費、行政規費…）
RECEIPT_CATEGORY_COUNSELING = "C"
RECEIPT_CATEGORY_OTHER = "O"

# 收據狀態尾碼（v7 格式）：見 01 §C4 / 09 §7——這是唯一還沒被診療所正式
# 拍板的編號規則，所以做成可切換（settings.RECEIPT_NUMBER_FORMAT）。
RECEIPT_STATE_ISSUED = 1
RECEIPT_STATE_REPRINT = 2
RECEIPT_STATE_VOID = 3


def _allocate(db: Session, scope: str, backfill_sql: str | None = None, params: dict | None = None) -> int:
    """配一個號給 scope。第一次碰到這個 scope 時用 backfill_sql 決定起點。"""
    row = db.execute(
        text("UPDATE number_sequences SET last_seq = last_seq + 1 WHERE scope = :scope RETURNING last_seq"),
        {"scope": scope},
    ).first()
    if row:
        return int(row[0])

    start = 1
    if backfill_sql:
        existing = db.execute(text(backfill_sql), params or {}).scalar()
        start = int(existing or 0) + 1

    # ON CONFLICT 是為了防「兩個交易同時發現 scope 不存在」——後到的那個
    # 會走 DO UPDATE 分支拿到 start+1，而不是撞 primary key。
    row = db.execute(
        text(
            "INSERT INTO number_sequences (scope, last_seq) VALUES (:scope, :start) "
            "ON CONFLICT (scope) DO UPDATE SET last_seq = number_sequences.last_seq + 1 "
            "RETURNING last_seq"
        ),
        {"scope": scope, "start": start},
    ).first()
    return int(row[0])


# ─────────────────────────────────────────────────────────────────────────
# 病歷號（兩段式編號的第二段，見 資料庫結構與資料轉換規範 §4.1）
# ─────────────────────────────────────────────────────────────────────────

def next_case_number(db: Session, *, on_date: date, national_id_last2: str) -> str:
    """一般個案病歷號：{YY}{流水4碼}{身分證末2碼}，例 26000145。"""
    yy = f"{on_date.year % 100:02d}"
    seq = _allocate(
        db,
        f"case:{yy}",
        "SELECT MAX(CAST(SUBSTRING(case_number FROM 3 FOR 4) AS INTEGER)) FROM cases "
        "WHERE case_number LIKE :p AND LENGTH(case_number) = 8",
        {"p": f"{yy}%"},
    )
    return f"{yy}{seq:04d}{national_id_last2}"


def next_couple_number(db: Session, *, on_date: date) -> str:
    """伴侶案病歷號：C{YY}{流水4碼}，例 C260003。伴侶案沒有身分證。"""
    yy = f"{on_date.year % 100:02d}"
    seq = _allocate(
        db,
        f"couple:{yy}",
        "SELECT MAX(CAST(SUBSTRING(case_number FROM 4 FOR 4) AS INTEGER)) FROM cases "
        "WHERE case_number LIKE :p AND LENGTH(case_number) = 7",
        {"p": f"C{yy}%"},
    )
    return f"C{yy}{seq:04d}"


# ─────────────────────────────────────────────────────────────────────────
# 預約編號（資料庫結構與資料轉換規範 §4.4）
# ─────────────────────────────────────────────────────────────────────────

def next_appointment_number(db: Session, *, on_date: date, therapist_code: str) -> str:
    """R-{YYYYMMDD}-{心理師代碼}-{流水3碼}，例 R-20260516-T018-001。"""
    d = on_date.strftime("%Y%m%d")
    prefix = f"R-{d}-{therapist_code}-"
    seq = _allocate(
        db,
        f"appt:{d}:{therapist_code}",
        "SELECT MAX(CAST(RIGHT(appointment_number, 3) AS INTEGER)) FROM appointments "
        "WHERE appointment_number LIKE :p",
        {"p": f"{prefix}%"},
    )
    return f"{prefix}{seq:03d}"


# ─────────────────────────────────────────────────────────────────────────
# 收據編號 —— 兩種格式可切換（settings.RECEIPT_NUMBER_FORMAT）
#
#   v7      A{YYYYMMDD}{C|O}{流水3碼}-{狀態}   例 A20260801C021-1
#           館別A ＋ 年月日 ＋ 分類 ＋ 流水 ＋ 檢核碼（1開立 / 2重印 / 3作廢）
#           這是診療所在 v7 原型上看過的格式，所以當預設。
#
#   legacy  R{YYYYMMDD}{流水4碼}                例 R202608010021
#           舊程式碼一直在用的格式，保留是因為 01 §C4 這條規則還沒正式定案，
#           診療所若改主意，改一個設定就切回去。
# ─────────────────────────────────────────────────────────────────────────

def next_receipt_no(db: Session, *, on_date: date, category: str = RECEIPT_CATEGORY_COUNSELING) -> str:
    """配一個新的「開立」收據號。

    注意：session_records.receipt_no 與 receipts.receipt_no 共用同一個 scope。
    舊程式碼是兩張表各自數各自的，同一天會產出兩個一模一樣的字串（兩張表
    所以沒撞到 unique，但人看了會以為是同一張收據）——這裡一併修掉。
    """
    d = on_date.strftime("%Y%m%d")
    if settings.RECEIPT_NUMBER_FORMAT == "legacy":
        seq = _allocate(
            db,
            f"receipt-legacy:{d}",
            "SELECT MAX(CAST(SUBSTRING(receipt_no FROM 10 FOR 4) AS INTEGER)) FROM ("
            "  SELECT receipt_no FROM session_records WHERE receipt_no LIKE :p"
            "  UNION ALL SELECT receipt_no FROM receipts WHERE receipt_no LIKE :p"
            ") x",
            {"p": f"R{d}%"},
        )
        return f"R{d}{seq:04d}"

    seq = _allocate(
        db,
        f"receipt:{d}:{category}",
        "SELECT MAX(CAST(SUBSTRING(receipt_no FROM 11 FOR 3) AS INTEGER)) FROM ("
        "  SELECT receipt_no FROM session_records WHERE receipt_no LIKE :p"
        "  UNION ALL SELECT receipt_no FROM receipts WHERE receipt_no LIKE :p"
        ") x",
        {"p": f"A{d}{category}%"},
    )
    return f"A{d}{category}{seq:03d}-{RECEIPT_STATE_ISSUED}"


def receipt_variant(receipt_no: str, state: int) -> str:
    """同一張收據的重印(-2)／作廢(-3) 版本，沿用同一個 base。

    這就是「重印與作廢共用 base、另開一列」的做法——重印軌跡自動成立，
    不必另外建一張重印紀錄表。legacy 格式沒有狀態尾碼的位置，直接原樣回傳。
    """
    if settings.RECEIPT_NUMBER_FORMAT == "legacy":
        return receipt_no
    base = receipt_no.rsplit("-", 1)[0] if "-" in receipt_no else receipt_no
    return f"{base}-{state}"


def parse_receipt_no(receipt_no: str) -> dict | None:
    """拆解收據號，看不懂就回 None。給不變量檢查器與前端顯示用。

    容忍 ledger 拆帳產生的 -A / -B 尾碼（見 routers/ledger.py 的 split）。
    """
    if not receipt_no:
        return None
    core = receipt_no
    split_suffix = None
    if core.endswith("-A") or core.endswith("-B"):
        core, split_suffix = core[:-2], core[-1]

    if core.startswith("A") and "-" in core:
        body, state = core.rsplit("-", 1)
        if len(body) == 13 and body[1:9].isdigit() and body[10:13].isdigit() and state.isdigit():
            return {
                "format": "v7", "venue": body[0], "date": body[1:9], "category": body[9],
                "seq": int(body[10:13]), "state": int(state), "split": split_suffix,
            }
    if core.startswith("R") and len(core) == 13 and core[1:].isdigit():
        return {
            "format": "legacy", "venue": None, "date": core[1:9], "category": None,
            "seq": int(core[9:13]), "state": RECEIPT_STATE_ISSUED, "split": split_suffix,
        }
    return None


def next_product_receipt_no(db: Session, *, on_date: date) -> str:
    """商品販售收據：P{YYYYMMDD}{流水4碼}。與諮商收據分開流水。"""
    d = on_date.strftime("%Y%m%d")
    seq = _allocate(
        db,
        f"product:{d}",
        "SELECT MAX(CAST(RIGHT(receipt_no, 4) AS INTEGER)) FROM product_sales WHERE receipt_no LIKE :p",
        {"p": f"P{d}%"},
    )
    return f"P{d}{seq:04d}"


def next_venue_rental_no(db: Session, *, on_date: date) -> str:
    """場地租借單號：V{YYYYMMDD}{流水3碼}。與預約編號分開流水——場地租借
    沒有心理師也沒有個案，混在一起編號只會讓兩邊都難查。"""
    d = on_date.strftime("%Y%m%d")
    seq = _allocate(
        db,
        f"venue:{d}",
        "SELECT MAX(CAST(RIGHT(rental_no, 3) AS INTEGER)) FROM venue_rentals WHERE rental_no LIKE :p",
        {"p": f"V{d}%"},
    )
    return f"V{d}{seq:03d}"


# ─────────────────────────────────────────────────────────────────────────
# 核銷編號
# ─────────────────────────────────────────────────────────────────────────

def next_claim_no(db: Session, *, on_date: date) -> str:
    """機構核銷案容器編號：{YYYYMM}-{流水2碼}，例 202607-01。見 07 §4.3。"""
    prefix = on_date.strftime("%Y%m")
    seq = _allocate(
        db,
        f"claim_case:{prefix}",
        "SELECT MAX(CAST(RIGHT(claim_no, 2) AS INTEGER)) FROM inst_claim_cases WHERE claim_no LIKE :p",
        {"p": f"{prefix}-%"},
    )
    return f"{prefix}-{seq:02d}"


def next_batch_suffix(db: Session, *, base: str) -> str:
    """舊 claim_batches 的重複編號後綴。第一次回傳 base 本身，之後 base-2、base-3…"""
    seq = _allocate(
        db,
        f"claim_batch:{base}",
        "SELECT COUNT(*) FROM claim_batches WHERE batch_number LIKE :p",
        {"p": f"{base}%"},
    )
    return base if seq == 1 else f"{base}-{seq}"


# ─────────────────────────────────────────────────────────────────────────
# 媒合派案碼
# ─────────────────────────────────────────────────────────────────────────

def next_referral_code(db: Session, *, on_date: date) -> str:
    """派案碼：{YYMMDD}{流水3碼}，例 260801001。建立諮商需求表時產生。"""
    prefix = on_date.strftime("%y%m%d")
    seq = _allocate(
        db,
        f"referral:{prefix}",
        "SELECT MAX(CAST(RIGHT(referral_code, 3) AS INTEGER)) FROM referrals WHERE referral_code LIKE :p",
        {"p": f"{prefix}%"},
    )
    return f"{prefix}{seq:03d}"
