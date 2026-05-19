# Backward-compatibility shim — real implementation moved to app.services.pdf package
from app.services.pdf import generate_self_pay_receipt, generate_institution_claim_form  # noqa: F401
