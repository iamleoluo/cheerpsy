"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { SESSION_TYPE } from "@/lib/format";

interface Row {
  id: number;
  session_date: string;
  case_name: string | null;
  session_type: string;
  claim_batch_id: number;
  batch_number: string | null;
  admin_verified: boolean;
  rejected_reason: string | null;
  locked: boolean;
}

interface Doc {
  id: number;
  doc_type: string;
  doc_type_label: string;
  file_name: string;
  note: string | null;
  uploaded_at: string;
}

const DOC_TYPES: [string, string][] = [
  ["receipt", "領據"],
  ["monthly_list", "月次清冊表"],
  ["other", "其他（銀行帳戶／證照／同意書）"],
];

export default function DocsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"pending" | "confirmed">("pending");
  const [rows, setRows] = useState<Row[]>([]);
  const [sel, setSel] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadFor, setUploadFor] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setRows(await clientFetch(`/claim-batches/my/pending-docs?confirmed=${tab === "confirmed"}`, token));
      setSel([]);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, tab]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(path: string) {
    if (sel.length === 0) return;
    try {
      await clientFetch(`/claim-batches/my/${path}`, token, {
        method: "POST",
        body: JSON.stringify({ record_ids: sel }),
      });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold">文件確認</h1>
      <p className="mt-1 text-sm text-gray-500">
        機構核銷需雙重把關：心理師確認文件 ＋ 行政核對，兩者皆完成該筆才算齊備。
        只要有一筆未齊備，整案就無法轉「待送出」。
      </p>

      <div className="mb-4 mt-4 flex gap-2 border-b border-gray-200">
        {([["pending", "未確認"], ["confirmed", "已確認文件"]] as const).map(([k, label]) => (
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
            {k === "pending" && tab === "pending" && rows.length > 0 && (
              <span className="ml-1.5 rounded-full bg-red-500 px-1.5 text-[10px] text-white">{rows.length}</span>
            )}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {sel.length > 0 && (
        <div className="mb-3 flex items-center gap-2 rounded-lg bg-primary-50 px-4 py-2 text-sm">
          已選 {sel.length} 筆
          {tab === "pending" ? (
            <button onClick={() => act("confirm-docs")} className="ml-auto rounded-lg bg-primary-600 px-3 py-1.5 text-white">
              批次確認文件
            </button>
          ) : (
            <button onClick={() => act("withdraw-docs")} className="ml-auto rounded-lg border border-gray-300 bg-white px-3 py-1.5">
              撤回（行政尚未核對者）
            </button>
          )}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="w-10 px-3 py-3">
                <input
                  type="checkbox"
                  checked={rows.length > 0 && sel.length === rows.filter((r) => !r.locked).length}
                  onChange={(e) => setSel(e.target.checked ? rows.filter((r) => !r.locked).map((r) => r.id) : [])}
                />
              </th>
              <th className="px-3 py-3">日期</th>
              <th className="px-3 py-3">個案</th>
              <th className="px-3 py-3">類型</th>
              <th className="px-3 py-3">核銷案號</th>
              <th className="px-3 py-3">狀態</th>
              <th className="px-3 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-gray-400">
                {tab === "pending" ? "目前沒有待確認的文件" : "尚無已確認的文件"}
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className={`border-b border-gray-100 last:border-0 ${r.rejected_reason ? "bg-red-50" : ""}`}>
                <td className="px-3 py-2.5">
                  <input
                    type="checkbox"
                    disabled={r.locked}
                    checked={sel.includes(r.id)}
                    onChange={(e) => setSel((s) => (e.target.checked ? [...s, r.id] : s.filter((x) => x !== r.id)))}
                  />
                </td>
                <td className="px-3 py-2.5">{r.session_date}</td>
                <td className="px-3 py-2.5 font-medium">{r.case_name}</td>
                <td className="px-3 py-2.5">{SESSION_TYPE[r.session_type] ?? r.session_type}</td>
                <td className="px-3 py-2.5 font-mono text-xs">{r.batch_number ?? r.claim_batch_id}</td>
                <td className="px-3 py-2.5">
                  {r.rejected_reason ? (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700" title={r.rejected_reason}>
                      已退回補件
                    </span>
                  ) : r.admin_verified ? (
                    <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">行政已核對（鎖定）</span>
                  ) : tab === "confirmed" ? (
                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">已確認，待行政核對</span>
                  ) : (
                    <span className="text-xs text-gray-500">待確認</span>
                  )}
                  {r.rejected_reason && (
                    <div className="mt-0.5 text-[11px] text-red-600">退回原因：{r.rejected_reason}</div>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <button onClick={() => setUploadFor(r.claim_batch_id)} className="text-xs text-primary-600 hover:underline">
                    上傳附件
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        只看得到自己負責的紀錄；核銷案編號、日期、個案、方案可見，但不顯示請款金額與收據。
        若機構不需心理師文件，行政可在核銷案端豁免，此頁該筆即消失。
      </p>

      {uploadFor && (
        <UploadModal
          token={token}
          batchId={uploadFor}
          onClose={() => setUploadFor(null)}
        />
      )}
    </div>
  );
}

function UploadModal({ token, batchId, onClose }: { token: string; batchId: number; onClose: () => void }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [docType, setDocType] = useState("receipt");
  const [fileName, setFileName] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDocs(await clientFetch(`/claim-batches/${batchId}/documents`, token));
    } catch (e: any) {
      setErr(e.message);
    }
  }, [token, batchId]);

  useEffect(() => {
    load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await clientFetch(`/claim-batches/${batchId}/documents`, token, {
        method: "POST",
        body: JSON.stringify({ doc_type: docType, file_name: fileName, note: note || null }),
      });
      setFileName("");
      setNote("");
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">核銷案附件</h2>
        <p className="mb-4 text-sm text-gray-500">
          一次上傳完畢，行政要核銷時再下載。三類：領據／月次清冊表／其他。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

        <form onSubmit={add} className="mb-4 space-y-2 rounded-lg border border-gray-200 p-3">
          <select value={docType} onChange={(e) => setDocType(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
            {DOC_TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input
            required
            value={fileName}
            onChange={(e) => setFileName(e.target.value)}
            placeholder="檔案名稱，如 20260722林家妤-諮商摘要表"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="備註（選填）" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button type="submit" className="w-full rounded-lg bg-primary-600 px-3 py-2 text-sm text-white">新增附件</button>
        </form>

        <div className="space-y-1">
          {docs.length === 0 && <p className="text-sm text-gray-400">尚無附件</p>}
          {docs.map((d) => (
            <div key={d.id} className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm">
              <span className="rounded bg-white px-1.5 py-0.5 text-xs text-gray-600">{d.doc_type_label}</span>
              <span className="truncate">{d.file_name}</span>
              <button
                onClick={async () => {
                  await clientFetch(`/claim-batches/${batchId}/documents/${d.id}`, token, { method: "DELETE" });
                  load();
                }}
                className="ml-auto shrink-0 text-xs text-red-500 hover:underline"
              >
                刪除
              </button>
            </div>
          ))}
        </div>

        <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
          目前只登錄檔名與備註，實際檔案上傳待接上物件儲存後補。
        </p>

        <div className="mt-4 flex justify-end">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">關閉</button>
        </div>
      </div>
    </div>
  );
}
