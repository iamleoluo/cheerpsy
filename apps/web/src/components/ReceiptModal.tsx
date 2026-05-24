"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ReceiptType = "single_session" | "batch" | "product";

interface ReceiptPreview {
  receipt_number: string;
  issue_date: string;
  payee: string;
  fee_category: string;
  quantity_label: string;
  quantity: string;
  total_amount: number;
  note: string;
  show_tax_id: boolean;
}

interface ReceiptModalProps {
  token: string;
  type: ReceiptType;
  sourceId: number;
  onClose: () => void;
}

function typePath(type: ReceiptType): string {
  if (type === "single_session") return "single-session";
  if (type === "batch") return "batch";
  return "product";
}

export default function ReceiptModal({ token, type, sourceId, onClose }: ReceiptModalProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Form state
  const [receiptNumber, setReceiptNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [payee, setPayee] = useState("");
  const [feeCat, setFeeCat] = useState("");
  const [qtyLabel, setQtyLabel] = useState("");
  const [qty, setQty] = useState("");
  const [total, setTotal] = useState(0);
  const [note, setNote] = useState("");
  const [showTaxId, setShowTaxId] = useState(false);
  const [taxId, setTaxId] = useState("");

  useEffect(() => {
    const path = typePath(type);
    fetch(`${API_URL}/receipts/${path}/${sourceId}/preview`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json() as Promise<ReceiptPreview>;
      })
      .then((d) => {
        setReceiptNumber(d.receipt_number);
        setIssueDate(d.issue_date);
        setPayee(d.payee);
        setFeeCat(d.fee_category);
        setQtyLabel(d.quantity_label);
        setQty(d.quantity);
        setTotal(d.total_amount);
        setNote(d.note);
        setShowTaxId(d.show_tax_id);
      })
      .catch((e) => setError(`載入失敗：${e.message}`))
      .finally(() => setLoading(false));
  }, [token, type, sourceId]);

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const path = typePath(type);
      const res = await fetch(`${API_URL}/receipts/${path}/${sourceId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          receipt_number: receiptNumber,
          issue_date: issueDate,
          payee,
          fee_category: feeCat,
          quantity_label: qtyLabel,
          quantity: qty,
          total_amount: total,
          note,
          tax_id: showTaxId ? taxId : "",
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `receipt-${receiptNumber}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (e: any) {
      setError(`開立失敗：${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-[500px] max-h-[90vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-base font-semibold">開立收據</h3>

        {loading ? (
          <div className="py-8 text-center text-sm text-gray-400">載入中...</div>
        ) : (
          <div className="space-y-3">
            {/* 收據編號 */}
            <div className="flex gap-3">
              <label className="flex-1">
                <span className="text-xs font-medium text-gray-700">收據編號</span>
                <input
                  type="text"
                  value={receiptNumber}
                  onChange={(e) => setReceiptNumber(e.target.value)}
                  className="mt-1 block w-full rounded border px-2 py-1.5 text-sm font-mono"
                />
              </label>
              <label className="w-36">
                <span className="text-xs font-medium text-gray-700">開立日期</span>
                <input
                  type="text"
                  value={issueDate}
                  onChange={(e) => setIssueDate(e.target.value)}
                  placeholder="114/04/29"
                  className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
                />
              </label>
            </div>

            {/* 姓名/單位 */}
            <label className="block">
              <span className="text-xs font-medium text-gray-700">姓名 / 單位</span>
              <input
                type="text"
                value={payee}
                onChange={(e) => setPayee(e.target.value)}
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>

            {/* 統一編號（可開關） */}
            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-700">
                <input
                  type="checkbox"
                  checked={showTaxId}
                  onChange={(e) => setShowTaxId(e.target.checked)}
                  className="accent-primary-600"
                />
                加入統一編號
              </label>
              {showTaxId && (
                <input
                  type="text"
                  value={taxId}
                  onChange={(e) => setTaxId(e.target.value)}
                  placeholder="8 碼統一編號"
                  className="mt-1 block w-full rounded border px-2 py-1.5 text-sm font-mono"
                  maxLength={8}
                />
              )}
            </div>

            {/* 收費項目（唯讀） */}
            <div className="flex gap-3">
              <div className="flex-1">
                <p className="text-xs font-medium text-gray-700">收費項目</p>
                <p className="mt-1 rounded border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm">{feeCat}</p>
              </div>
              <div className="w-28">
                <p className="text-xs font-medium text-gray-700">{qtyLabel}</p>
                <p className="mt-1 rounded border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm">{qty}</p>
              </div>
              <div className="w-28">
                <p className="text-xs font-medium text-gray-700">總計</p>
                <p className="mt-1 rounded border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm font-medium">
                  ${total.toLocaleString()}
                </p>
              </div>
            </div>

            {/* 備註 */}
            <label className="block">
              <span className="text-xs font-medium text-gray-700">備註（自動帶入，可修改）</span>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
          </div>
        )}

        {error && <p className="mt-3 text-xs text-red-500">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={loading || submitting}
            className="rounded bg-primary-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {submitting ? "產生中..." : "確認開立 PDF"}
          </button>
        </div>
      </div>
    </div>
  );
}
