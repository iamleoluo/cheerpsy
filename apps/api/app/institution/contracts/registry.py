"""合約模組分派表。見 09 §3.1／§3.3——首批 5 份合約逐一升級成專屬模組。

兩層分派：
    ① BY_ID：明確指定某個 contract_id 用哪個模組。最精確，但 id 要等
       合約真的建檔才知道，不適合寫死給「範例資料」用。
    ② BY_CONTRACT_NAME：依 inst_contracts.name 完全比對。seed_plans.py
       建的示範資料用的就是這個——名稱是行政自己取的、通常穩定，且比
       瞎猜 id 更貼近「新裝一個環境、重新 seed 一次」也要能生效的需求。
       缺點是行政如果把合約改名，就會退回通用版——這是刻意的安全退化
       （寧可退回通用版，也不要匹配錯合約套用錯的呈現邏輯）。

沒被登記的合約（① ② 都沒對到）一律走 ContractModule 預設
（= GenericContractModule）——這正是「先做 5 個、其餘先能用」這個決定
能成立的地方（09 §6 第 3 步）。
"""

from __future__ import annotations

from app.institution.contracts.base import ContractModule
from app.institution.contracts.count_based_claim import CountBasedClaimModule
from app.institution.contracts.health_bureau import HealthBureauModule
from app.institution.contracts.kickback import KickbackModule
from app.institution.contracts.military import MilitaryModule
from app.institution.contracts.venue_rental import VenueRentalModule
from app.institution.models.contract import InstContract

BY_ID: dict[int, type[ContractModule]] = {}

# 首批 5 份（09 §3.3，依 seed_plans.py 的實際合約名稱比對）：
#   衛生局市民 — 次數分級計價
#   國軍心理照護方案 — 合約層級金額池
#   市政府人事處 — 次數制核銷（人事處系列共用同一套邏輯）
#   教支中心 — 回饋制
#   鉅微借場地 — 無心理師勞務、不計額度
BY_CONTRACT_NAME: dict[str, type[ContractModule]] = {
    "衛生局市民": HealthBureauModule,
    "國軍心理照護方案": MilitaryModule,
    "市政府人事處": CountBasedClaimModule,
    "教支中心": KickbackModule,
    "鉅微借場地": VenueRentalModule,
}


def get_module_for_contract(contract: InstContract) -> ContractModule:
    """呼叫端已經查過 contract（例如 panel 端點先確認過存在），直接傳物件
    進來，不在這裡另開連線重查一次。"""
    module_cls = BY_ID.get(contract.id) or BY_CONTRACT_NAME.get(contract.name)
    return (module_cls or ContractModule)()
