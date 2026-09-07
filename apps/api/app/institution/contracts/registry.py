"""合約模組分派表。見 09 §3.1／§3.3——首批 5 份合約（衛生局／國軍／
家防中心／聊心茶室／鉅微）逐一升級成專屬模組時，在這裡加一行對應：

    REGISTRY: dict[int, type[ContractModule]] = {
        1: HealthBureauModule,   # 衛生局
        2: MilitaryModule,       # 國軍
    }

key 是 inst_contracts.id（實際合約建檔後才會知道，不是寫死在合約名稱猜的）。
沒被登記的合約一律走 ContractModule 預設（= GenericContractModule）——
這正是「先做 5 個、其餘先能用」這個決定能成立的地方（09 §6 第 3 步）。
"""

from __future__ import annotations

from app.institution.contracts.base import ContractModule

REGISTRY: dict[int, type[ContractModule]] = {}


def get_module_for_contract(contract_id: int) -> ContractModule:
    module_cls = REGISTRY.get(contract_id, ContractModule)
    return module_cls()
