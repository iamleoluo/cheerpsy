"""機構額度三態的流轉。

恆等式（由 DB CHECK 強制）：已使用 + 已預約 + 已預留 = 個人上限

流轉規則（原型 plans「額度流轉」）：
    加入方案      → 全數進已預留            (0/0/N)
    排一次預約    → 已預留 → 已預約          (0/1/N-1)
    報到「已到」  → 已預約 → 已使用          (1/0/N-1)
    未到／取消    → 已預約 → 退回已預留      (0/0/N)
    個案結案      → 已預留＋已預約全數釋出   (used/0/0)

所有函式都只改記憶體中的物件，由呼叫端負責 commit。
"""

from fastapi import HTTPException

from app.models.case_institution_quota import CaseInstitutionQuota


def _assert_invariant(q: CaseInstitutionQuota) -> None:
    total = q.used_count + q.booked_count + q.reserved_count
    if total != q.total_count:
        raise HTTPException(
            status_code=500,
            detail=(
                f"額度三態不一致（quota {q.id}）："
                f"{q.used_count}+{q.booked_count}+{q.reserved_count} != {q.total_count}"
            ),
        )


def reserve_to_booked(q: CaseInstitutionQuota) -> None:
    """排預約：已預留 → 已預約。"""
    if q.reserved_count < 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"機構額度不足：已使用 {q.used_count}／已預約 {q.booked_count}／"
                f"已預留 {q.reserved_count}，共 {q.total_count} 次。請改為自費。"
            ),
        )
    q.reserved_count -= 1
    q.booked_count += 1
    _assert_invariant(q)


def booked_to_used(q: CaseInstitutionQuota) -> None:
    """報到已到：已預約 → 已使用。"""
    if q.booked_count < 1:
        raise HTTPException(status_code=409, detail=f"額度狀態異常：quota {q.id} 沒有已預約的次數可轉為已使用")
    q.booked_count -= 1
    q.used_count += 1
    if q.reserved_count == 0 and q.booked_count == 0:
        q.status = "exhausted"
    _assert_invariant(q)


def booked_to_reserved(q: CaseInstitutionQuota) -> None:
    """未到／取消預約：已預約 → 退回已預留。"""
    if q.booked_count < 1:
        return  # 已經退過或本來就沒佔用，視為無操作
    q.booked_count -= 1
    q.reserved_count += 1
    if q.status == "exhausted":
        q.status = "active"
    _assert_invariant(q)


def release_on_close(q: CaseInstitutionQuota) -> None:
    """個案結案：已預留＋已預約全數釋出回方案總池，只保留已使用的歷史。"""
    q.total_count = q.used_count
    q.booked_count = 0
    q.reserved_count = 0
    q.status = "closed"
    _assert_invariant(q)


def remaining(q: CaseInstitutionQuota) -> int:
    """還能再排幾次預約（已預留的部分）。"""
    return q.reserved_count


def is_last_session(q: CaseInstitutionQuota) -> bool:
    """只剩最後一次 → 前端整列標黃、日曆方塊加紅框、提示下次轉自費。"""
    return (q.reserved_count + q.booked_count) == 1
