"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";
import ReceiptModal from "@/components/ReceiptModal";

const helpContent: HelpContent = {
  title: "商品販售",
  guideId: "products",
  overview: "登記非預約的其他商品銷售（如繪本、教具），以現金為主。每筆自動產生收據編號，並彙整進營運報表的「其他商品販售」。",
  sections: [
    {
      heading: "新增銷售",
      type: "steps",
      items: [
        "點「＋新增銷售」",
        "填日期、品名、單價、數量、付款方式",
        "儲存後自動產生收據編號（P 開頭）",
      ],
    },
    {
      heading: "作廢",
      type: "tips",
      items: [
        "登記錯誤或退貨時點「作廢」，作廢後不列入報表",
        "作廢需填事由，會記錄於稽核日誌",
      ],
    },
  ],
};

interface ProductSale {
  id: number;
  sale_date: string;
  product_name: string;
  amount: number;
  quantity: number;
  payment_method: string | null;
  payment_note: string | null;
  receipt_no: string | null;
  is_void: boolean;
  void_reason: string | null;
}

const PM_LABELS: Record<string, string> = { cash: "現金", transfer: "匯款" };

export default function ProductsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [helpOpen, setHelpOpen] = useState(false);
  const [sales, setSales] = useState<ProductSale[]>([]);
  const [loading, setLoading] = useState(true);
  const now = new Date();
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [showCreate, setShowCreate] = useState(false);
  const [receiptSaleId, setReceiptSaleId] = useState<number | null>(null);

  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [fDate, setFDate] = useState(today);
  const [fName, setFName] = useState("");
  const [fAmount, setFAmount] = useState("");
  const [fQty, setFQty] = useState("1");
  const [fMethod, setFMethod] = useState("cash");
  const [fNote, setFNote] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchSales = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await clientFetch(`/product-sales?month=${month}`, token);
      setSales(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token, month]);

  useEffect(() => { fetchSales(); }, [fetchSales]);

  if (!token) return <p>Loading...</p>;

  const create = async () => {
    if (!fName.trim() || !fAmount) { alert("請填品名與金額"); return; }
    setSaving(true);
    try {
      await clientFetch("/product-sales", token, {
        method: "POST",
        body: JSON.stringify({
          sale_date: fDate,
          product_name: fName.trim(),
          amount: Number(fAmount),
          quantity: Number(fQty) || 1,
          payment_method: fMethod,
          payment_note: fNote.trim() || null,
        }),
      });
      setShowCreate(false);
      setFName(""); setFAmount(""); setFQty("1"); setFNote("");
      fetchSales();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  const voidSale = async (id: number) => {
    const reason = prompt("作廢事由：");
    if (reason === null) return;
    try {
      await clientFetch(`/product-sales/${id}/void`, token, {
        method: "PUT",
        body: JSON.stringify({ reason: reason || null }),
      });
      fetchSales();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const total = sales.filter((s) => !s.is_void).reduce((sum, s) => sum + s.amount * s.quantity, 0);

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      {receiptSaleId !== null && (
        <ReceiptModal token={token} type="product" sourceId={receiptSaleId} onClose={() => setReceiptSaleId(null)} />
      )}
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">商品販售</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
            <span>ℹ️</span> 說明
          </button>
          <button onClick={() => setShowCreate(true)} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700">
            ＋新增銷售
          </button>
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <span className="text-sm text-gray-500">本月合計：<strong className="text-gray-900">${total.toLocaleString()}</strong>（{sales.filter((s) => !s.is_void).length} 筆）</span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">收據編號</th>
              <th className="px-4 py-3">品名</th>
              <th className="px-4 py-3">單價</th>
              <th className="px-4 py-3">數量</th>
              <th className="px-4 py-3">小計</th>
              <th className="px-4 py-3">付款</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : sales.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">本月尚無商品銷售</td></tr>
            ) : sales.map((s) => (
              <tr key={s.id} className={`hover:bg-gray-50 ${s.is_void ? "opacity-50 line-through" : ""}`}>
                <td className="px-4 py-3 whitespace-nowrap">{s.sale_date}</td>
                <td className="px-4 py-3 font-mono text-xs">{s.receipt_no ?? "-"}</td>
                <td className="px-4 py-3">{s.product_name}</td>
                <td className="px-4 py-3">${s.amount.toLocaleString()}</td>
                <td className="px-4 py-3">{s.quantity}</td>
                <td className="px-4 py-3">${(s.amount * s.quantity).toLocaleString()}</td>
                <td className="px-4 py-3 text-xs">{PM_LABELS[s.payment_method ?? "cash"] ?? s.payment_method}</td>
                <td className="px-4 py-3 no-underline">
                  {s.is_void ? (
                    <span className="text-xs text-red-500">已作廢</span>
                  ) : (
                    <div className="flex gap-2">
                      <button onClick={() => setReceiptSaleId(s.id)} className="text-xs text-primary-600 hover:underline">開立收據</button>
                      <button onClick={() => voidSale(s.id)} className="text-xs text-red-500 hover:underline">作廢</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowCreate(false)}>
          <div className="w-96 rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-base font-semibold">新增商品銷售</h3>
            <div className="space-y-3">
              <label className="block">
                <span className="text-xs font-medium text-gray-700">日期</span>
                <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5 text-sm" />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-gray-700">品名</span>
                <input type="text" value={fName} onChange={(e) => setFName(e.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5 text-sm" />
              </label>
              <div className="flex gap-2">
                <label className="flex-1">
                  <span className="text-xs font-medium text-gray-700">單價</span>
                  <input type="number" value={fAmount} onChange={(e) => setFAmount(e.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5 text-sm" />
                </label>
                <label className="w-24">
                  <span className="text-xs font-medium text-gray-700">數量</span>
                  <input type="number" value={fQty} onChange={(e) => setFQty(e.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5 text-sm" />
                </label>
              </div>
              <label className="block">
                <span className="text-xs font-medium text-gray-700">付款方式</span>
                <select value={fMethod} onChange={(e) => setFMethod(e.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5 text-sm">
                  <option value="cash">現金</option>
                  <option value="transfer">匯款</option>
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-gray-700">備註（選填）</span>
                <input type="text" value={fNote} onChange={(e) => setFNote(e.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5 text-sm" />
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setShowCreate(false)} className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">取消</button>
              <button onClick={create} disabled={saving} className="rounded bg-primary-600 px-4 py-1.5 text-sm text-white hover:bg-primary-700 disabled:opacity-50">
                {saving ? "儲存中…" : "儲存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
