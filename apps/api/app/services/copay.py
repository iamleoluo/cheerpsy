"""個案自付款的統一判準 — V2升級計畫 09 §1.4a / §5。

你的裁示逐字：

    「機構案有時候會需要自費款。例如一筆 1600 元的款項，可能有 400 元是個案要
    自付，剩下 1200 元是機構補助。那這 400 元自費款也要納入整個自費流程」
    「自費部分：在櫃檯當下就要看到」
    「機構案部分：基本上是行政人員點開特定頁面才需要看到」

也就是說分界**不是「自費案 vs 機構案」，而是「這筆錢的付款方是誰」**：
一筆機構預約會產生兩段各自獨立的錢，個案自付那段走日常收款動線，機構請款
那段走合約專頁的核銷，兩者互不相干。

09 §5 把「統一自付款查詢」列為**高優先**的後端缺口，原因是現行
`/ledger/self-pay-unpaid` 過濾 `funding_source == 'self_pay'`，於是
**沒有任何查詢會把機構案的自付額顯示成未收**。實測：現行查詢看到 80 筆，
統一查詢看到 85 筆——那 5 筆機構案自付額（$2,000）本來完全是隱形的。

這個模組是那個統一來源。日報表、應收帳冊、報到收款、營運總覽待辦一律
從這裡取判準，不各自兜一套。
"""

from datetime import date

from sqlalchemy import Numeric, case, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.models.appointment import Appointment
from app.models.case import Case
from app.models.session_record import SessionRecord


def due_expr():
    """這筆場次「個案要付多少」。

    `case_payable` 有值就用它（機構案的自付額）；沒有就是純自費／舊路徑，
    整筆都是個案要付的。優待減免要扣掉——舊查詢漏了這一項。
    """
    return func.coalesce(SessionRecord.case_payable, SessionRecord.amount) - func.coalesce(
        SessionRecord.discount_amount, 0
    )


def _is_institution_expr():
    """這筆有沒有機構那一段錢。"""
    return or_(
        func.coalesce(SessionRecord.institution_payable, 0) > 0,
        SessionRecord.funding_source == "institution",
    )


def collected_expr():
    """個案自付款收到了沒。

    兩條路徑的真值來源不同，這是刻意的（見 models/session_record.py）：

    · 機構案 —— **只認 `copay_collected_at`**。它的 `payment_status` 語意是
      「機構請款進度」（unpaid→claiming→claimed），跟個案付錢了沒無關。
      實測資料庫裡有 4 筆 `payment_status='claimed'` 但自付額還沒收的紀錄，
      若拿 payment_status 判斷就會誤判成已收。

    · 純自費 —— 認 `copay_collected_at`，**或**舊的 `payment_status`。
      需要 OR 是因為舊端點 `PUT /ledger/{id}/pay` 只寫 payment_status
      不寫 copay_collected_at（實測有 9 筆這種歷史資料）。
    """
    return case(
        (_is_institution_expr(), SessionRecord.copay_collected_at.isnot(None)),
        else_=or_(
            SessionRecord.copay_collected_at.isnot(None),
            SessionRecord.payment_status.in_(("paid", "claimed")),
        ),
    )


def outstanding_query(
    db: Session,
    *,
    on_date: date | None = None,
    therapist_id: int | None = None,
    with_relations: bool = True,
) -> Query:
    """還欠著個案自付款的場次。**不分 funding_source。**

    只回「真的還欠錢」的：應收 > 0（機構全額補助的 $0 不算欠）、未作廢、未收。
    """
    q = db.query(SessionRecord).filter(
        SessionRecord.is_void.is_(False),
        due_expr() > 0,
        collected_expr().is_(False),
    )
    if on_date is not None:
        q = q.filter(SessionRecord.session_date == on_date)
    if therapist_id is not None:
        q = q.filter(SessionRecord.therapist_id == therapist_id)
    if with_relations:
        q = q.options(
            joinedload(SessionRecord.appointment)
            .joinedload(Appointment.case)
            .joinedload(Case.institution),
            joinedload(SessionRecord.appointment).joinedload(Appointment.therapist),
        )
    return q.order_by(SessionRecord.session_date)


def outstanding_total(db: Session, *, on_date: date | None = None) -> tuple[int, float]:
    """(筆數, 金額)。給統計列用，不撈整批資料。"""
    q = db.query(
        func.count(SessionRecord.id),
        func.coalesce(func.sum(due_expr()), 0).cast(Numeric(12, 2)),
    ).filter(
        SessionRecord.is_void.is_(False),
        due_expr() > 0,
        collected_expr().is_(False),
    )
    if on_date is not None:
        q = q.filter(SessionRecord.session_date == on_date)
    n, amt = q.one()
    return int(n or 0), float(amt or 0)
