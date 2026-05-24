from pydantic import BaseModel


class ReceiptPreview(BaseModel):
    """GET /receipts/.../preview 回傳，前端用於預填開立表單。"""
    receipt_number: str
    issue_date: str
    payee: str
    fee_category: str
    quantity_label: str
    quantity: str
    total_amount: int
    note: str
    show_tax_id: bool  # True 時前端預設展開統一編號欄


class ReceiptRequest(BaseModel):
    """POST /receipts/... 接收，行政人員確認後送出產生 PDF。"""
    receipt_number: str
    issue_date: str
    payee: str
    fee_category: str
    quantity_label: str
    quantity: str
    total_amount: int
    note: str = ""
    tax_id: str = ""  # 非空時加入收據統一編號列
