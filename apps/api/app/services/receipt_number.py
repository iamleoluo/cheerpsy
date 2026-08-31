"""收據編號產生器（心智圖 §四.1）。

規則：館別 + 開立年月日 + 流水號3碼 + 分類 + 檢核碼
      A20260716C001-1

  館別   A＝永康館
  分類   C＝諮商／O＝其他（商品販售）
  檢核碼 1＝開立／2＝重印／3＝作廢

`invoices` 是收據的**單一真相**（Phase 1b 起）。舊格式 R.../P... 的收據
在 Phase 1b 已回填成 invoices 列並原樣保留，產號時會跳過它們。
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.invoice import Invoice

BRANCH_YONGKANG = "A"
CATEGORY_COUNSELING = "C"
CATEGORY_OTHER = "O"

CHECK_ISSUED = 1
CHECK_REPRINT = 2
CHECK_VOIDED = 3


def format_receipt_no(branch: str, d: date, category: str, seq: int, check_code: int) -> str:
    return f"{branch}{d.strftime('%Y%m%d')}{category}{seq:03d}-{check_code}"


def next_receipt_no(
    db: Session,
    d: date,
    category: str = CATEGORY_COUNSELING,
    branch: str = BRANCH_YONGKANG,
) -> tuple[str, int]:
    """回傳 (收據編號, 流水號)。

    流水號依「當日 + 分類」計數，只數新格式的收據 —— 舊的 R/P 開頭不重編、
    也不佔用新的流水號。
    """
    prefix = f"{branch}{d.strftime('%Y%m%d')}{category}"
    n = (
        db.query(func.count(Invoice.id))
        .filter(
            Invoice.invoice_number.like(f"{prefix}%"),
            Invoice.print_seq == 0,  # 只數原始開立，重印不佔流水號
        )
        .scalar()
        or 0
    )
    seq = n + 1
    return format_receipt_no(branch, d, category, seq, CHECK_ISSUED), seq


def issue(
    db: Session,
    d: date,
    *,
    session_record_id: int | None = None,
    product_sale_id: int | None = None,
    created_by: int | None = None,
) -> Invoice:
    """開立收據（檢核碼 -1）。"""
    if (session_record_id is None) == (product_sale_id is None):
        raise ValueError("session_record_id 與 product_sale_id 需且僅需擇一")
    category = CATEGORY_COUNSELING if session_record_id else CATEGORY_OTHER
    number, _ = next_receipt_no(db, d, category)
    inv = Invoice(
        invoice_number=number,
        session_record_id=session_record_id,
        product_sale_id=product_sale_id,
        status="active",
        branch_code=BRANCH_YONGKANG,
        category=category,
        print_seq=0,
        check_code=CHECK_ISSUED,
        created_by=created_by,
    )
    db.add(inv)
    db.flush()
    return inv


def reprint(db: Session, invoice: Invoice, created_by: int | None = None) -> Invoice:
    """重印（檢核碼 -2）。沿用同一組流水號，只遞增 print_seq。

    Q8 定案（2026-08-31）：收據就是**重印**；若要重開，**必須先作廢**。
    沒有第三條路徑，因此已作廢的收據在此直接拒絕。
    """
    if invoice.status == "voided":
        raise ValueError("已作廢的收據不可重印，請走作廢後重開")
    base = invoice.invoice_number.rsplit("-", 1)[0]
    invoice.print_seq += 1
    invoice.check_code = CHECK_REPRINT
    invoice.invoice_number = f"{base}-{CHECK_REPRINT}"
    db.flush()
    return invoice


def void(db: Session, invoice: Invoice, reason: str, voided_by: int | None = None) -> Invoice:
    """作廢（檢核碼 -3）。編號不回收，重開會取新的流水號。"""
    base = invoice.invoice_number.rsplit("-", 1)[0]
    invoice.status = "voided"
    invoice.check_code = CHECK_VOIDED
    invoice.invoice_number = f"{base}-{CHECK_VOIDED}"
    invoice.void_reason = reason
    db.flush()
    return invoice
