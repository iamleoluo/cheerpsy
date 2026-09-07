"""Layer 3：合約模組的基底類別。見 V2升級計畫 09 §3.1（分層架構）。

一份合約 = 一個 ContractModule。這一層只做「組裝 Layer 2 的原語」，
產出這份合約專屬的 read model（build_panel 的回傳值）——寫入動作一律走
共用的 write API（09 §3.2 讀專屬、寫共用），這裡不放任何寫入邏輯。

紀律（09 §3.6，抄在這裡提醒自己）：
    ① 合約模組不准直接寫 DB，只能組裝 primitives/ 與 claims/service 提供
       的原語。原語做不到的事，是「該擴充原語」的訊號，不是在這裡硬寫。
    ② 面板上的候選名單，必須跟寫入端驗證用同一個函式算（claims/service.py
       的 list_uncollected／list_per_case_count_candidates 已經是這樣設計）。

預設實作（GenericContractModule，見 generic.py）覆蓋 09 §3.4 定義的
「通用版／工具式」：不主動判斷、把所有可用的區塊都攤開讓行政自己操作。
54 份合約裡，還沒被升級成專屬模組的那些全部走這條路——這是「先做 5 個、
其餘先能用」這個決定能成立的技術前提（09 §6 第 3 步）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.institution.models.contract import InstContract


class ContractModule:
    """合約模組的介面。子類別只需要覆寫 build_panel()；不覆寫就是通用版
    （因為 build_panel 的預設實作就是呼叫 generic.build_generic_panel）。
    """

    def build_panel(self, db: Session, contract: InstContract) -> dict:
        from app.institution.contracts.generic import build_generic_panel

        return build_generic_panel(db, contract)
