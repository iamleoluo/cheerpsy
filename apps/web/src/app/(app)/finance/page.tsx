"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

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

const statusLabels: Record<string, string> = {
  active: "有效",
  voided: "作廢",
};

const statusColors: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  voided: "bg-red-100 text-red-600",
};

export default function FinancePage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [voidingId, setVoidingId] = useState<number | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [error, setError] = useState("");

  const fetchInvoices = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter) params.set("status", filter);
      const qs = params.toString();
      const data = await clientFetch(`/invoices${qs ? `?${qs}` : ""}`, token);
      setInvoices(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, filter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleVoid = async () => {
    if (!token || !voidingId || !voidReason) return;
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

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">財務核銷</h1>
        {userRole !== "therapist" && (
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            + 開立收據
          </button>
        )}
      </div>

      <div className="mb-4">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">全部</option>
          <option value="active">有效</option>
          <option value="voided">作廢</option>
        </select>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>
      )}

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
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[inv.status] ?? "bg-gray-100"}`}>
                      {statusLabels[inv.status] ?? inv.status}
                    </span>
                    {inv.void_reason && (
                      <div className="mt-1 text-xs text-gray-400">{inv.void_reason}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {inv.created_at
                      ? new Date(inv.created_at).toLocaleDateString("zh-TW")
                      : "-"}
                  </td>
                  <td className="px-4 py-3">
                    {inv.status === "active" && userRole !== "therapist" && (
                      <button
                        onClick={() => setVoidingId(inv.id)}
                        className="text-xs text-red-600 hover:underline"
                      >
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
                required
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
        {error && (
          <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>
        )}
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
              {saving ? "開立中..." : "開立收據"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
