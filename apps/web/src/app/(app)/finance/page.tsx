"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";

/* ───── main page ───── */

export default function FinancePage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const [tab, setTab] = useState<"invoices" | "payouts" | "petty">("invoices");

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">財務管理</h1>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["invoices", "收據管理"],
            ["payouts", "心理師酬勞"],
            ["petty", "零用金"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "border-b-2 border-primary-600 text-primary-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "invoices" && <InvoicesTab token={token} userRole={userRole} />}
      {tab === "payouts" && <PayoutsTab token={token} userRole={userRole} />}
      {tab === "petty" && <PettyCashTab token={token} userRole={userRole} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 1 — 收據管理
   ═══════════════════════════════════════════════ */

interface InvoiceItem {
  id: number;
  invoice_number: string;
  appointment_id: number;
  appointment_number: string | null;
  case_name: string | null;
  therapist_name: string | null;
  amount: number | null;
  status: string;
  void_reason: string | null;
  created_at: string | null;
}

interface ExecutedAppointment {
  id: number;
  appointment_number: string;
  case_name: string | null;
  therapist_name: string | null;
  amount: number;
  status: string;
}

const invoiceStatusLabels: Record<string, string> = { active: "有效", voided: "作廢" };
const invoiceStatusColors: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  voided: "bg-red-100 text-red-600",
};

function InvoicesTab({ token, userRole }: { token: string; userRole: string }) {
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [voidingId, setVoidingId] = useState<number | null>(null);
  const [voidReason, setVoidReason] = useState("");

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter) params.set("status", filter);
      const qs = params.toString();
      const data = await clientFetch(`/invoices${qs ? `?${qs}` : ""}`, token);
      setInvoices(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, filter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleVoid = async () => {
    if (!voidingId || !voidReason) return;
    try {
      await clientFetch(`/invoices/${voidingId}/void`, token, {
        method: "PUT",
        body: JSON.stringify({ void_reason: voidReason }),
      });
      setVoidingId(null);
      setVoidReason("");
      fetchInvoices();
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">全部</option>
          <option value="active">有效</option>
          <option value="voided">作廢</option>
        </select>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/invoices", token, "invoices.csv")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              匯出 CSV
            </button>
          )}
          {userRole !== "therapist" && (
            <button
              onClick={() => setShowCreate(true)}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              + 開立收據
            </button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">收據編號</th>
              <th className="px-4 py-3">預約編號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">金額</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">開立日期</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">載入中...</td>
              </tr>
            ) : invoices.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">尚無收據</td>
              </tr>
            ) : (
              invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{inv.invoice_number}</td>
                  <td className="px-4 py-3 font-mono text-xs">{inv.appointment_number ?? "-"}</td>
                  <td className="px-4 py-3">{inv.case_name ?? "-"}</td>
                  <td className="px-4 py-3">{inv.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">${inv.amount?.toLocaleString() ?? "-"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${invoiceStatusColors[inv.status] ?? "bg-gray-100"}`}
                    >
                      {invoiceStatusLabels[inv.status] ?? inv.status}
                    </span>
                    {inv.void_reason && (
                      <div className="mt-1 text-xs text-gray-400">{inv.void_reason}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {inv.created_at ? new Date(inv.created_at).toLocaleDateString("zh-TW") : "-"}
                  </td>
                  <td className="px-4 py-3">
                    {inv.status === "active" && userRole !== "therapist" && (
                      <button onClick={() => setVoidingId(inv.id)} className="text-xs text-red-600 hover:underline">
                        作廢
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateInvoiceModal
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            fetchInvoices();
          }}
        />
      )}

      {voidingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">作廢收據</h2>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">作廢原因 *</span>
              <textarea
                value={voidReason}
                onChange={(e) => setVoidReason(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => { setVoidingId(null); setVoidReason(""); }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleVoid}
                disabled={!voidReason}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                確認作廢
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CreateInvoiceModal({
  token,
  onClose,
  onCreated,
}: {
  token: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [appointments, setAppointments] = useState<ExecutedAppointment[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    clientFetch("/appointments?status=executed", token)
      .then(setAppointments)
      .catch(() => {});
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await clientFetch("/invoices", token, {
        method: "POST",
        body: JSON.stringify({ appointment_id: parseInt(selectedId) }),
      });
      onCreated();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">開立收據</h2>
        {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">已執行的預約 *</span>
            <select
              required
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">請選擇</option>
              {appointments.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.appointment_number} - {a.case_name} (${a.amount})
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {saving ? "開立中..." : "開立收據"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 2 — 心理師酬勞月結
   ═══════════════════════════════════════════════ */

interface Payout {
  id: number;
  therapist_id: number;
  therapist_name: string | null;
  payout_month: string;
  total_amount: number;
  session_count: number;
  status: string;
  paid_at: string | null;
}

interface PayoutSession {
  session_id: number;
  session_date: string;
  amount: number;
  therapist_share: number;
  fee_category: string;
  session_type: string;
}

const payoutStatusLabels: Record<string, string> = { pending: "待發放", paid: "已發放" };
const payoutStatusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  paid: "bg-green-100 text-green-700",
};
const sessionTypeLabels: Record<string, string> = { in_person: "現場", online: "線上", home_visit: "到宅" };

function PayoutsTab({ token, userRole }: { token: string; userRole: string }) {
  const now = new Date();
  const [filterMonth, setFilterMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [detailModal, setDetailModal] = useState<{ payoutId: number; name: string } | null>(null);
  const [details, setDetails] = useState<PayoutSession[]>([]);

  const fetchPayouts = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterMonth ? `?payout_month=${filterMonth}` : "";
      const data = await clientFetch(`/payouts${params}`, token);
      setPayouts(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, filterMonth]);

  useEffect(() => {
    fetchPayouts();
  }, [fetchPayouts]);

  const handleGenerate = async () => {
    if (!filterMonth) return;
    setGenerating(true);
    try {
      const result = await clientFetch("/payouts/generate", token, {
        method: "POST",
        body: JSON.stringify({ payout_month: filterMonth }),
      });
      alert(`${result.month} 酬勞已產生，共 ${result.payouts_created} 位心理師`);
      fetchPayouts();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handlePay = async (id: number) => {
    if (!confirm("確認已發放此酬勞？")) return;
    try {
      await clientFetch(`/payouts/${id}/pay`, token, { method: "PUT" });
      fetchPayouts();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const showDetails = async (payoutId: number, name: string) => {
    setDetailModal({ payoutId, name });
    try {
      const data = await clientFetch(`/payouts/${payoutId}/details`, token);
      setDetails(data.sessions);
    } catch {
      setDetails([]);
    }
  };

  const totalAmount = payouts.reduce((s, p) => s + p.total_amount, 0);
  const pendingCount = payouts.filter((p) => p.status === "pending").length;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={filterMonth}
            onChange={(e) => setFilterMonth(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          {payouts.length > 0 && (
            <span className="text-sm text-gray-500">
              合計 ${totalAmount.toLocaleString()} · {pendingCount > 0 ? `${pendingCount} 筆待發放` : "全部已發放"}
            </span>
          )}
        </div>
        {userRole === "admin" && (
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {generating ? "產生中..." : "產生酬勞"}
          </button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">月份</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3 text-right">場次</th>
              <th className="px-4 py-3 text-right">酬勞金額</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">發放日期</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">載入中...</td>
              </tr>
            ) : payouts.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  尚無酬勞資料（管理員可產生月結酬勞）
                </td>
              </tr>
            ) : (
              payouts.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{p.payout_month}</td>
                  <td className="px-4 py-3 font-medium">{p.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3 text-right">{p.session_count}</td>
                  <td className="px-4 py-3 text-right font-medium">${p.total_amount.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${payoutStatusColors[p.status] ?? "bg-gray-100"}`}
                    >
                      {payoutStatusLabels[p.status] ?? p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {p.paid_at ? new Date(p.paid_at).toLocaleDateString("zh-TW") : "-"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => showDetails(p.id, p.therapist_name ?? "")}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        明細
                      </button>
                      {userRole === "admin" && p.status === "pending" && (
                        <button onClick={() => handlePay(p.id)} className="text-xs text-green-600 hover:underline">
                          確認發放
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {detailModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">{detailModal.name} — 酬勞明細</h2>
            {details.length === 0 ? (
              <p className="text-sm text-gray-400">無明細資料</p>
            ) : (
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th className="px-4 py-2">日期</th>
                      <th className="px-4 py-2">類型</th>
                      <th className="px-4 py-2">費目</th>
                      <th className="px-4 py-2 text-right">金額</th>
                      <th className="px-4 py-2 text-right">師酬</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {details.map((d) => (
                      <tr key={d.session_id}>
                        <td className="px-4 py-2">{d.session_date}</td>
                        <td className="px-4 py-2">{sessionTypeLabels[d.session_type] ?? d.session_type}</td>
                        <td className="px-4 py-2">{d.fee_category}</td>
                        <td className="px-4 py-2 text-right">${d.amount.toLocaleString()}</td>
                        <td className="px-4 py-2 text-right font-medium">${d.therapist_share.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setDetailModal(null)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 3 — 零用金
   ═══════════════════════════════════════════════ */

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

function PettyCashTab({ token, userRole }: { token: string; userRole: string }) {
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
        <p className="text-sm text-gray-500">
          目前餘額：
          <span className={`font-bold ${currentBalance >= 0 ? "text-green-600" : "text-red-600"}`}>
            ${currentBalance.toLocaleString()}
          </span>
        </p>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/petty-cash", token, "petty_cash.csv")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              匯出 CSV
            </button>
          )}
          {userRole !== "therapist" && (
            <button
              onClick={() => setShowForm(true)}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              + 新增紀錄
            </button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">類別</th>
              <th className="px-4 py-3">說明</th>
              <th className="px-4 py-3 text-right">金額</th>
              <th className="px-4 py-3 text-right">餘額</th>
              <th className="px-4 py-3">收據備註</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">載入中...</td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">尚無零用金紀錄</td>
              </tr>
            ) : (
              records.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{r.date}</td>
                  <td className="px-4 py-3">{categoryLabels[r.category] ?? r.category}</td>
                  <td className="px-4 py-3">{r.description ?? "-"}</td>
                  <td
                    className={`px-4 py-3 text-right font-medium ${r.amount >= 0 ? "text-green-600" : "text-red-600"}`}
                  >
                    {r.amount >= 0 ? "+" : ""}${r.amount.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">${r.balance_after.toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{r.receipt_note ?? "-"}</td>
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
        {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">日期 *</span>
              <input
                required
                type="date"
                value={form.date}
                onChange={(e) => setField("date", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">類型</span>
              <select
                value={form.type}
                onChange={(e) => setField("type", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="expense">支出</option>
                <option value="income">補充</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">金額 *</span>
              <input
                required
                type="number"
                min="0"
                step="1"
                value={form.amount}
                onChange={(e) => setField("amount", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">類別</span>
              <select
                value={form.category}
                onChange={(e) => setField("category", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
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
            <span className="mb-1 block text-xs text-gray-500">說明</span>
            <input
              value={form.description}
              onChange={(e) => setField("description", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">收據備註</span>
            <input
              value={form.receipt_note}
              onChange={(e) => setField("receipt_note", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              placeholder="收據編號或備註"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {saving ? "儲存中..." : "儲存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
