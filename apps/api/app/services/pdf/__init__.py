"""Config-driven PDF generation package.

Backward-compatible API (identical signatures to the legacy
`app.services.pdf_generator` functions) plus the new `generate_pdf`
template-registry entrypoint.
"""
from datetime import date

from .engine import DocumentSpec, render, render_multi
from .templates import TEMPLATES, generate_pdf

__all__ = [
    "generate_self_pay_receipt",
    "generate_institution_claim_form",
    "generate_pdf",
    "DocumentSpec",
    "render",
    "render_multi",
    "TEMPLATES",
]


def generate_self_pay_receipt(
    batch_number: str,
    case_name: str,
    period_start: date | None,
    period_end: date | None,
    records: list[dict],
    total_amount: float,
) -> bytes:
    return generate_pdf("self_pay_receipt", {
        "batch_number": batch_number,
        "case_name": case_name,
        "period_start": period_start,
        "period_end": period_end,
        "records": records,
        "total_amount": total_amount,
    })


def generate_institution_claim_form(
    batch_number: str,
    institution_name: str,
    period_start: date | None,
    period_end: date | None,
    records: list[dict],
    total_amount: float,
    external_ref: str | None = None,
) -> bytes:
    return generate_pdf("institution_claim_form", {
        "batch_number": batch_number,
        "institution_name": institution_name,
        "period_start": period_start,
        "period_end": period_end,
        "records": records,
        "total_amount": total_amount,
        "external_ref": external_ref,
    })
