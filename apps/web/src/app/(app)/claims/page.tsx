"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { SESSION_TYPE, money, todayISO } from "@/lib/format";

interface Batch {
  id: number;
  batch_number: string;
  type: string;
  is_legacy?: boolean;
  institution_id: number | null;
  institution_name?: string | null;
  period_start: string | null;
  period_end: string | null;
  total_amount: number;
  status: string;
  void_reason?: string | null;
  voided_at?: string | null;
}

interface SelRecord {
  id: number;
  session_date: string;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  session_type: string;
  self_pay_amount: number;
  institution_claim_amount: number;
  in_this_batch: boolean;
  locked_by_batch_id: number | null;
  therapist_confirmed: boolean;
  admin_verified: boolean;
  rejected_reason: string | null;
}

interface Plan {
  id: number;
  name: string;
  institution_name: string | null;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  collecting: { label: "收集中", cls: "bg-amber-100 text-amber-700" },
  ready: { label: "待送出", cls: "bg-blue-100 text-blue-700" },
  submitted: { label: "已送出", cls: "bg-violet-100 text-violet-700" },
  received: { label: "已結案", cls: "bg-green-100 text-green-700" },
  voided: { label: "已作廢", cls: "bg-gray-200 text-gray-500" },
};

export default function ClaimsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const role = (session?.user as any)?.role;
  const [tab, setTab] = useState<"list" | "docs" | "void">("list");
  const [batches, setBatches] = useState<Batch[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [voidFor, setVoidFor] = useState<Batch | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [bs, ps] = await Promise.all([
        clientFetch("/claim-batches", token),
        clientFetch("/institution-plans", token).catch(() => []),
      ]);
      setBatches(bs);
      setPlans(ps);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const active = batches.filter((b) => b.status !== "voided" && !b.is_legacy);
  const voided = batches.filter((b) => b.status === "voided");
  const legacy = batches.filter((b) => b.is_legacy);

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold">機構核銷案</h1>
      <p className="mt-1 text-sm text-gray-500">
        每月 1 號起只要有方案預約即可建案，之後每天把紀錄加進去，讓心理師能提早上傳文件。
        期間為<b>參考區間</b>，缺口與重疊只提示、不阻擋。
      </p>

      <div className="mb-4 mt-4 flex gap-2 border-b border-gray-200">
        {([
          ["list", `核銷案列表 (${active.length})`],
          ["docs", "文件狀態與退件"],
          ["void", `作廢處理 (${voided.length})`],
        ] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm ${
              tab === k
                ? "border-b-2 border-primary-600 font-medium text-primary-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {legacy.length > 0 && tab === "list" && (
        <div className="mb-4 rounded-lg bg-gray-100 px-4 py-2.5 text-sm text-gray-600">
          另有 {legacy.length} 筆自費月結批次為<b>歷史資料</b>（唯讀）。自費月結已改走
          「應收帳冊 → 月結」分頁，不再於此建立。
        </div>
      )}

      {(tab === "list" || tab === "void") && (
        <div className="space-y-3">
          {(tab === "list" ? active : voided).length === 0 && (
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-10 text-center text-gray-400">
              {tab === "list" ? "尚無核銷案" : "沒有作廢的核銷案"}
            </div>
          )}
          {(tab === "list" ? active : voided).map((b) => {
            const st = STATUS[b.status] ?? { label: b.status, cls: "bg-gray-100" };
            const open = openId === b.id;
            return (
              <div key={b.id} className={`overflow-hidden rounded-xl border bg-white ${b.status === "voided" ? "border-gray-200 opacity-70" : "border-gray-200"}`}>
                <div className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <button onClick={() => setOpenId(open ? null : b.id)} className="text-gray-400">
                    {open ? "▾" : "▸"}
                  </button>
                  <span className="font-mono text-sm">{b.batch_number}</span>
                  <span className="text-sm font-medium">{b.institution_name ?? "—"}</span>
                  <span className="text-xs text-gray-500">
                    {b.period_start ?? "—"} ~ {b.period_end ?? "—"}
                  </span>
                  <span className={`rounded px-1.5 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
                  <span className="ml-auto tabular-nums">{money(b.total_amount)}</span>
                  {b.status !== "voided" && ["admin", "accountant"].includes(role) && (
                    <button onClick={() => setVoidFor(b)} className="text-xs text-red-500 hover:underline">
                      作廢
                    </button>
                  )}
                </div>
                {b.void_reason && (
                  <div className="border-t border-gray-100 bg-gray-50 px-4 py-2 text-xs text-gray-600">
                    作廢原因：{b.void_reason}
                    <span className="ml-3 text-gray-400">
                      紀錄已脫離本案並回到可核銷池；機構額度與心理師酬勞不受影響
                    </span>
                  </div>
                )}
                {open && <BatchDetail token={token} batch={b} plans={plans} onChanged={load} />}
              </div>
            );
          })}
        </div>
      )}

      {tab === "docs" && <DocsStatus token={token} batches={active} onChanged={load} />}

      {voidFor && (
        <VoidModal
          token={token}
          batch={voidFor}
          onClose={() => setVoidFor(null)}
          onDone={() => {
            setVoidFor(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function BatchDetail({
  token,
  batch,
  plans,
  onChanged,
}: {
  token: string;
  batch: Batch;
  plans: Plan[];
  onChanged: () => void;
}) {
  const [selPlans, setSelPlans] = useState<number[]>([]);
  const [planId, setPlanId] = useState<number | 0>(0);
  const [data, setData] = useState<{ records: SelRecord[]; hint: string | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadPlans = useCallback(async () => {
    try {
      const p = await clientFetch(`/claim-batches/${batch.id}/plans`, token);
      setSelPlans(p.map((x: any) => x.plan_id));
      if (p.length && !planId) setPlanId(p[0].plan_id);
    } catch { /* ignore */ }
  }, [token, batch.id, planId]);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  const loadRecords = useCallback(async () => {
    if (!planId) return;
    try {
      setData(await clientFetch(`/claim-batches/${batch.id}/selectable-records?plan_id=${planId}`, token));
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }, [token, batch.id, planId]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  async function savePlans(ids: number[]) {
    try {
      await clientFetch(`/claim-batches/${batch.id}/plans`, token, {
        method: "PUT",
        body: JSON.stringify({ plan_ids: ids }),
      });
      setSelPlans(ids);
      onChanged();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function toggleRecord(r: SelRecord) {
    try {
      if (r.in_this_batch) {
        await clientFetch(`/claim-batches/${batch.id}/records/${r.id}`, token, { method: "DELETE" });
      } else {
        await clientFetch(`/claim-batches/${batch.id}/records`, token, {
          method: "POST",
          body: JSON.stringify({ record_ids: [r.id] }),
        });
      }
      loadRecords();
      onChanged();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="border-t border-gray-100 bg-gray-50 px-4 py-4">
      {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

      <div className="mb-3">
        <div className="mb-1 text-xs font-medium text-gray-600">
          涵蓋方案（可同時選多個一起核銷）
        </div>
        <div className="flex flex-wrap gap-2">
          {plans.map((p) => {
            const on = selPlans.includes(p.id);
            return (
              <button
                key={p.id}
                onClick={() => savePlans(on ? selPlans.filter((x) => x !== p.id) : [...selPlans, p.id])}
                className={`rounded-lg border px-2 py-1 text-xs ${
                  on ? "border-primary-500 bg-primary-50 text-primary-700" : "border-gray-300 bg-white"
                }`}
              >
                {p.institution_name} — {p.name}
              </button>
            );
          })}
          {plans.length === 0 && <span className="text-xs text-gray-400">尚無機構方案</span>}
        </div>
      </div>

      {selPlans.length > 0 && (
        <div className="mb-2 flex items-center gap-2 text-xs">
          <span className="text-gray-600">從方案挑紀錄：</span>
          <select value={planId} onChange={(e) => setPlanId(Number(e.target.value))} className="rounded border border-gray-300 px-2 py-1">
            {plans.filter((p) => selPlans.includes(p.id)).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {data?.hint && (
        <div className="mb-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">⚠️ {data.hint}（提示，不阻擋）</div>
      )}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-xs">
            <thead className="border-b border-gray-200 bg-gray-50 text-left text-gray-500">
              <tr>
                <th className="w-8 px-2 py-2" />
                <th className="px-2 py-2">日期</th>
                <th className="px-2 py-2">姓名</th>
                <th className="px-2 py-2">心理師</th>
                <th className="px-2 py-2">類型</th>
                <th className="px-2 py-2 text-right">自付額</th>
                <th className="px-2 py-2 text-right">機構請款額</th>
                <th className="px-2 py-2">心理師確認</th>
                <th className="px-2 py-2">行政核對</th>
              </tr>
            </thead>
            <tbody>
              {data.records.length === 0 && (
                <tr><td colSpan={9} className="px-2 py-6 text-center text-gray-400">此方案期間內沒有可納入的紀錄</td></tr>
              )}
              {data.records.map((r) => (
                <tr key={r.id} className={`border-b border-gray-100 last:border-0 ${r.locked_by_batch_id ? "opacity-40" : ""}`}>
                  <td className="px-2 py-1.5">
                    <input
                      type="checkbox"
                      checked={r.in_this_batch}
                      disabled={!!r.locked_by_batch_id}
                      onChange={() => toggleRecord(r)}
                      title={r.locked_by_batch_id ? `已被核銷案 #${r.locked_by_batch_id} 佔用` : undefined}
                    />
                  </td>
                  <td className="px-2 py-1.5">{r.session_date}</td>
                  <td className="px-2 py-1.5 font-medium">{r.case_name}</td>
                  <td className="px-2 py-1.5">{r.therapist_name}</td>
                  <td className="px-2 py-1.5">{SESSION_TYPE[r.session_type] ?? r.session_type}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{money(r.self_pay_amount)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{money(r.institution_claim_amount)}</td>
                  <td className="px-2 py-1.5">{r.therapist_confirmed ? "已確認" : "待確認"}</td>
                  <td className="px-2 py-1.5">{r.admin_verified ? "已核對" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[11px] text-gray-400">
        子列表可逐筆增減紀錄。已被其他核銷案佔用的紀錄會鎖定不可選。
      </p>
    </div>
  );
}

function DocsStatus({ token, batches, onChanged }: { token: string; batches: Batch[]; onChanged: () => void }) {
  const [batchId, setBatchId] = useState<number | 0>(batches[0]?.id ?? 0);
  const [rows, setRows] = useState<SelRecord[]>([]);
  const [docs, setDocs] = useState<any[]>([]);
  const [rejectFor, setRejectFor] = useState<SelRecord | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!batchId) return;
    try {
      const [recs, ds] = await Promise.all([
        clientFetch(`/claim-batches/${batchId}/records`, token).catch(() => []),
        clientFetch(`/claim-batches/${batchId}/documents`, token).catch(() => []),
      ]);
      setRows(recs);
      setDocs(ds);
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }, [token, batchId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-sm">
        <span className="text-gray-500">核銷案</span>
        <select value={batchId} onChange={(e) => setBatchId(Number(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-1.5">
          {batches.map((b) => <option key={b.id} value={b.id}>{b.batch_number} · {b.institution_name}</option>)}
        </select>
      </div>

      {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

      <div className="mb-4 rounded-xl border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-4 py-2.5 text-sm font-medium">心理師上傳的附件</div>
        {docs.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-400">尚無附件</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {docs.map((d) => (
              <div key={d.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">{d.doc_type_label}</span>
                <span className="truncate">{d.file_name}</span>
                <span className="ml-auto text-xs text-gray-400">{d.therapist_name}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-3 py-3">日期</th>
              <th className="px-3 py-3">姓名</th>
              <th className="px-3 py-3">心理師確認</th>
              <th className="px-3 py-3">行政核對</th>
              <th className="px-3 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-400">此核銷案尚無紀錄</td></tr>
            )}
            {rows.map((r: any) => (
              <tr key={r.id} className={`border-b border-gray-100 last:border-0 ${r.rejected_reason ? "bg-red-50" : ""}`}>
                <td className="px-3 py-2.5">{r.session_date}</td>
                <td className="px-3 py-2.5 font-medium">{r.case_name}</td>
                <td className="px-3 py-2.5 text-xs">{r.therapist_confirmed ? "已確認" : "待確認"}</td>
                <td className="px-3 py-2.5 text-xs">{r.admin_verified ? "已核對" : "—"}</td>
                <td className="px-3 py-2.5">
                  <button onClick={() => setRejectFor(r)} className="text-xs text-red-500 hover:underline">
                    退回補件
                  </button>
                  {r.rejected_reason && (
                    <div className="mt-0.5 text-[11px] text-red-600">退回原因：{r.rejected_reason}</div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        退回是<b>單筆</b>操作，不影響同案其他紀錄；但只要有一筆未齊備，整案就無法轉「待送出」。
      </p>

      {rejectFor && (
        <RejectModal
          token={token}
          batchId={batchId as number}
          record={rejectFor}
          onClose={() => setRejectFor(null)}
          onDone={() => {
            setRejectFor(null);
            load();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function RejectModal({ token, batchId, record, onClose, onDone }: any) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await clientFetch(`/claim-batches/${batchId}/records/${record.id}/reject`, token, {
              method: "POST",
              body: JSON.stringify({ reason }),
            });
            onDone();
          } catch (e: any) {
            setErr(e.message);
          }
        }}
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="mb-1 text-lg font-bold">退回補件</h2>
        <p className="mb-4 text-sm text-gray-500">
          {record.case_name} · {record.session_date}
          <br />
          會清除該筆的心理師確認與行政核對，回「待提交」並通知心理師。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <textarea
          required
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="退回原因（必填）"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
          <button type="submit" className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white">確認退回</button>
        </div>
      </form>
    </div>
  );
}

function VoidModal({ token, batch, onClose, onDone }: any) {
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [warn, setWarn] = useState<string | null>(null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setErr(null);
          try {
            const r = await clientFetch(`/claim-batches/${batch.id}/void`, token, {
              method: "POST",
              body: JSON.stringify({ reason, password }),
            });
            if (r.warning) {
              setWarn(r.warning);
              setTimeout(onDone, 2500);
            } else {
              onDone();
            }
          } catch (e: any) {
            setErr(e.message);
          }
        }}
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="mb-1 text-lg font-bold">作廢核銷案 {batch.batch_number}</h2>
        <div className="mb-4 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600">
          作廢後：紀錄脫離本案、付款狀態退回未核銷、回到可核銷池可重新建案。
          <br />
          <b>機構額度不受影響</b>（額度在報到時就已扣除，與核銷無關）。
          <br />
          <b>心理師酬勞不受影響</b>（依已執行場次計算，與是否請款成功脫鉤）。
          <br />
          編號不回收，重開會取新流水號。
        </div>
        {batch.status === "received" && (
          <div className="mb-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
            ⚠️ 此案機構已撥款，作廢後的退款需另行處理。
          </div>
        )}
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        {warn && <div className="mb-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">{warn}</div>}
        <textarea
          required
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="作廢原因（必填）"
          className="mb-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          required
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="請輸入你的密碼以確認"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
          <button type="submit" className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white">確認作廢</button>
        </div>
      </form>
    </div>
  );
}
