"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch, exportCsv } from "@/lib/client-api";

/**
 * 零用金 — 從 /finance 搬出來（13 §D2）。
 *
 * /finance 與 /claims 兩頁的功能都已經被機構子系統與新的對帳頁取代，唯獨
 * 零用金沒有新落點——所以那兩頁一直不能刪，side bar 上掛著「（舊）」。
 *
 * 落點選 /daily 是因為零用金本來就是**現金對帳**：當天收了多少現金、付出去
 * 多少零用金、水位剩多少，是同一件事的兩半。放在一起看才對得起來。
 */

interface PettyCashItem {
  id: number;
  date: string;
  amount: number;
  category: string;
  description: string | null;
  receipt_note: string | null;
  balance_after: number;
}

const categoryLabels: Record<string, string> = {
  cleaning: "清潔費",
  supplies: "文具耗材",
  electricity: "電費",
  water: "水費",
  other: "其他",
};

export function PettyCashTab({ token, userRole }: { token: string; userRole: string }) {
  const [records, setRecords] = useState<PettyCashItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/petty-cash", token);
      setRecords(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  const currentBalance = records.length > 0 ? records[0].balance_after : 0;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-ink-3">
          目前餘額：
          <span className={`font-bold ${currentBalance >= 0 ? "text-st-done" : "text-st-danger"}`}>
            ${currentBalance.toLocaleString()}
          </span>
        </p>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/petty-cash", token, "petty_cash.csv")}
              className="rounded-lg border border-line-2 px-4 py-2 text-sm font-medium hover:bg-surface-2"
            >
              匯出 CSV
            </button>
          )}
          {userRole !== "therapist" && (
            <button
              onClick={() => setShowForm(true)}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active"
            >
              + 新增紀錄
            </button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-ink-3">
            <tr>
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">類別</th>
              <th className="px-4 py-3">說明</th>
              <th className="px-4 py-3 text-right">金額</th>
              <th className="px-4 py-3 text-right">餘額</th>
              <th className="px-4 py-3">收據備註</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-ink-3">載入中...</td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-ink-3">尚無零用金紀錄</td>
              </tr>
            ) : (
              records.map((r) => (
                <tr key={r.id} className="hover:bg-surface-2">
                  <td className="px-4 py-3">{r.date}</td>
                  <td className="px-4 py-3">{categoryLabels[r.category] ?? r.category}</td>
                  <td className="px-4 py-3">{r.description ?? "-"}</td>
                  <td
                    className={`px-4 py-3 text-right font-medium ${r.amount >= 0 ? "text-st-done" : "text-st-danger"}`}
                  >
                    {r.amount >= 0 ? "+" : ""}${r.amount.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">${r.balance_after.toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-ink-3">{r.receipt_note ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <PettyCashForm
          token={token}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            fetchRecords();
          }}
        />
      )}
    </div>
  );
}

function PettyCashForm({
  token,
  onClose,
  onSaved,
}: {
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    type: "expense",
    amount: "",
    category: "other",
    description: "",
    receipt_note: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const setField = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const amt = parseFloat(form.amount);
      await clientFetch("/petty-cash", token, {
        method: "POST",
        body: JSON.stringify({
          date: form.date,
          amount: form.type === "expense" ? -Math.abs(amt) : Math.abs(amt),
          category: form.category,
          description: form.description || null,
          receipt_note: form.receipt_note || null,
        }),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">新增零用金紀錄</h2>
        {error && <div className="mb-3 rounded-lg bg-st-danger-bg p-2 text-sm text-st-danger">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">日期 *</span>
              <input
                required
                type="date"
                value={form.date}
                onChange={(e) => setField("date", e.target.value)}
                className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">類型</span>
              <select
                value={form.type}
                onChange={(e) => setField("type", e.target.value)}
                className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
              >
                <option value="expense">支出</option>
                <option value="income">補充</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">金額 *</span>
              <input
                required
                type="number"
                min="0"
                step="1"
                value={form.amount}
                onChange={(e) => setField("amount", e.target.value)}
                className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">類別</span>
              <select
                value={form.category}
                onChange={(e) => setField("category", e.target.value)}
                className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
              >
                <option value="cleaning">清潔費</option>
                <option value="supplies">文具耗材</option>
                <option value="electricity">電費</option>
                <option value="water">水費</option>
                <option value="other">其他</option>
              </select>
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">說明</span>
            <input
              value={form.description}
              onChange={(e) => setField("description", e.target.value)}
              className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">收據備註</span>
            <input
              value={form.receipt_note}
              onChange={(e) => setField("receipt_note", e.target.value)}
              className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
              placeholder="收據編號或備註"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50"
            >
              {saving ? "儲存中..." : "儲存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
