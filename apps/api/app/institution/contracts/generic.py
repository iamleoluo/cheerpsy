"""通用版合約面板（09 §3.4「工具式」）。54 份合約裡還沒被升級成專屬模組
的，全部走這裡——系統不猜行政要幹嘛，把所有可用的區塊攤開讓行政自己操作。

每個方案自己的區塊組合由它的欄位決定（quota_pool_id／
default_quota_limit_numeric／period_limit／claim_grouping_mode／
requires_external_code），不是整份合約共用同一組——因為一份合約底下的
方案可能規則不同（09 §3.5 的區塊庫）。

只做「組裝」，不寫 DB（09 §3.6 紀律一）：這裡呼叫的都是 adapter.py／
claims/service.py 已經有的原語。
"""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.institution.claims import service as claims_service
from app.institution.models.claim_case import InstClaimCase
from app.institution.models.contract import InstContract
from app.institution.models.plan import InstPlan
from app.institution.models.quota_pool import InstQuotaPool
from app.institution.models.rate_rule import InstRateRule


def _load_checklist(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _plan_blocks(plan: InstPlan) -> list[str]:
    blocks: list[str] = []
    if plan.quota_pool_id is not None:
        blocks.append("quota_pool")
    elif plan.default_quota_limit_numeric is not None:
        blocks.append("quota_per_case")
    else:
        blocks.append("quota_unlimited")
    if plan.period_limit:
        blocks.append("period_sublimit")
    if plan.claim_grouping_mode == "per_case_count":
        blocks.append("claim_by_count")
    else:
        blocks.append("claim_by_period")
    blocks.append("claim_uncollected")
    if plan.requires_external_code:
        blocks.append("external_code")
    if _load_checklist(plan.admin_checklist) or _load_checklist(plan.therapist_checklist):
        blocks.append("doc_gate")
    blocks.append("rate_table")
    blocks.append("plan_params")
    return blocks


def build_generic_panel(db: Session, contract: InstContract) -> dict:
    from app.institution.adapter import InstitutionFundingProvider

    provider = InstitutionFundingProvider()
    plans = db.query(InstPlan).filter(InstPlan.contract_id == contract.id).order_by(InstPlan.id).all()

    plan_panels = []
    seen_claim_groups: set[str] = set()
    for plan in plans:
        blocks = _plan_blocks(plan)
        enrollments = provider.list_plan_enrollments(db, plan.id)

        pool_info = None
        if plan.quota_pool_id is not None:
            pool = db.query(InstQuotaPool).filter(InstQuotaPool.id == plan.quota_pool_id).first()
            if pool is not None:
                pool_info = {
                    "id": pool.id,
                    "name": pool.name,
                    "unit": pool.unit,
                    "total_limit": pool.total_limit,
                    "consumed_total": pool.consumed_total,
                    "remaining": (pool.total_limit - pool.consumed_total) if pool.total_limit is not None else None,
                }

        claim_group_key = plan.claim_group_key or plan.name
        uncollected = claims_service.list_uncollected(db, claim_group_key)
        candidates = None
        if plan.claim_grouping_mode == "per_case_count" and plan.claim_capacity:
            candidates = claims_service.list_per_case_count_candidates(db, claim_group_key, plan.claim_capacity)

        rate_rules = (
            db.query(InstRateRule).filter(InstRateRule.plan_id == plan.id).order_by(InstRateRule.sort_order).all()
        )

        plan_panels.append(
            {
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "quota_unit": plan.quota_unit,
                    "default_quota_limit_numeric": plan.default_quota_limit_numeric,
                    "period_limit": plan.period_limit,
                    "period_unit": plan.period_unit,
                    "compensation_mode": plan.compensation_mode,
                    "claim_group_key": claim_group_key,
                    "claim_grouping_mode": plan.claim_grouping_mode,
                    "claim_capacity": plan.claim_capacity,
                    "claim_timing": plan.claim_timing,
                    "requires_external_code": plan.requires_external_code,
                    "counts_toward_quota": plan.counts_toward_quota,
                    "is_active": plan.is_active,
                },
                "blocks": blocks,
                "enrollments": [e.model_dump() for e in enrollments],
                "quota_pool": pool_info,
                "claim_uncollected": [
                    {"id": r.id, "session_date": r.session_date, "case_id": r.case_id, "amount": r.institution_payable or r.amount}
                    for r in uncollected
                ],
                "claim_candidates": candidates,
                "admin_checklist": _load_checklist(plan.admin_checklist),
                "therapist_checklist": _load_checklist(plan.therapist_checklist),
                "rate_rules": [
                    {
                        "id": rr.id,
                        "sort_order": rr.sort_order,
                        "when_json": rr.when_json,
                        "unit_price": rr.unit_price,
                        "case_payable": rr.case_payable,
                        "label": rr.label,
                    }
                    for rr in rate_rules
                ],
            }
        )
        seen_claim_groups.add(claim_group_key)

    claim_cases = (
        db.query(InstClaimCase)
        .filter(InstClaimCase.claim_group_key.in_(seen_claim_groups))
        .order_by(InstClaimCase.claim_no.desc())
        .all()
        if seen_claim_groups
        else []
    )

    return {
        "contract": {
            "id": contract.id,
            "name": contract.name,
            "institution_id": contract.institution_id,
            "institution_name": contract.institution.name if contract.institution else None,
            "contact_name": contract.contact_name,
            "contact_phone": contract.contact_phone,
            "eligibility_note": contract.eligibility_note,
            "valid_from": contract.valid_from,
            "valid_until": contract.valid_until,
            "is_active": contract.is_active,
        },
        "module": "generic",
        "plans": plan_panels,
        "claim_cases": [
            {
                "id": c.id,
                "claim_no": c.claim_no,
                "claim_group_key": c.claim_group_key,
                "status": c.status,
                "record_count": len(c.lines),
                "applied_amount": c.applied_amount,
                "net_received": c.net_received,
            }
            for c in claim_cases
        ],
    }
