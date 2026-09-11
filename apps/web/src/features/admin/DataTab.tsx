"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch, exportCsv } from "@/lib/client-api";

/** 資料匯出入：CSV 匯出，以及三種模式（除錯／補登／清洗覆蓋）的匯入。 */

interface ImportResult {
  table: string;
  mode: string;
  total_rows: number;
  would_insert: number;
  would_update: number;
  would_skip: number;
  errors: { row: number; field: string; value?: string; message: string }[];
  warnings: { row: number; field: string; message: string }[];
  committed: boolean;
}

const IMPORT_TABLES = [
  { value: "session_records", label: "帳冊流水帳（session_records）" },
  { value: "cases", label: "個案（cases）" },
  { value: "users", label: "使用者帳號（users）" },
  { value: "institutions", label: "機構（institutions）" },
  { value: "petty_cash", label: "零用金（petty_cash）" },
  { value: "product_sales", label: "商品販售（product_sales）" },
];

export function DataTab({ token }: { token: string }) {
  const [tables, setTables] = useState<{ key: string; label: string; endpoint: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  // Import state
  const [impTable, setImpTable] = useState("session_records");
  const [impMode, setImpMode] = useState<"dry_run" | "supplement" | "clean">("dry_run");
  const [impFile, setImpFile] = useState<File | null>(null);
  const [impPassword, setImpPassword] = useState("");
  const [impResult, setImpResult] = useState<ImportResult | null>(null);
  const [impLoading, setImpLoading] = useState(false);
  const [impError, setImpError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(true);
  const [showWarnings, setShowWarnings] = useState(true);

  const fetchTables = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/export/tables", token);
      setTables(data);
    } catch {
      setTables([
        { key: "cases", label: "個案", endpoint: "/export/cases" },
        { key: "appointments", label: "預約", endpoint: "/export/appointments" },
        { key: "ledger", label: "帳冊流水帳", endpoint: "/export/ledger" },
        { key: "claim-batches", label: "核銷案", endpoint: "/export/claim-batches" },
        { key: "invoices", label: "收據", endpoint: "/export/invoices" },
        { key: "petty-cash", label: "零用金", endpoint: "/export/petty-cash" },
        { key: "users", label: "使用者", endpoint: "/export/users" },
        { key: "rooms", label: "諮商室", endpoint: "/export/rooms" },
        { key: "institutions", label: "機構", endpoint: "/export/institutions" },
        { key: "product-sales", label: "商品販售", endpoint: "/export/product-sales" },
        { key: "quota-templates", label: "方案範本", endpoint: "/export/quota-templates" },
        { key: "audit-log", label: "稽核日誌", endpoint: "/export/audit-log" },
      ]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchTables(); }, [fetchTables]);

  const handleDownload = async (table: { key: string; endpoint: string }) => {
    setDownloading(table.key);
    try {
      await exportCsv(table.endpoint, token, `${table.key}.csv`);
    } catch (e: any) {
      alert(`匯出失敗：${e.message}`);
    } finally {
      setDownloading(null);
    }
  };

  const handlePreview = async () => {
    if (!impFile) { setImpError("請先選擇 CSV 檔案"); return; }
    setImpLoading(true);
    setImpResult(null);
    setImpError(null);
    try {
      const form = new FormData();
      form.append("table", impTable);
      form.append("file", impFile);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/data-import/preview`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "預覽失敗" }));
        throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      }
      setImpResult(await res.json());
    } catch (e: any) {
      setImpError(e.message);
    } finally {
      setImpLoading(false);
    }
  };

  const handleImport = async () => {
    if (!impFile) { setImpError("請先選擇 CSV 檔案"); return; }
    if (impMode === "clean" && !impPassword) { setImpError("清洗模式需要輸入管理員密碼"); return; }
    if (!window.confirm(`確定要執行「${impMode === "supplement" ? "補登" : "清洗覆蓋"}」匯入？此操作不可撤銷。`)) return;
    setImpLoading(true);
    setImpResult(null);
    setImpError(null);
    try {
      const form = new FormData();
      form.append("table", impTable);
      form.append("file", impFile);
      if (impMode === "clean") form.append("admin_password", impPassword);
      const endpoint = impMode === "supplement" ? "supplement" : "clean";
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/data-import/${endpoint}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "匯入失敗" }));
        const detail = err.detail;
        if (detail && typeof detail === "object" && detail.errors) {
          setImpResult({ table: impTable, mode: impMode, total_rows: 0, would_insert: 0, would_update: 0, would_skip: 0, errors: detail.errors, warnings: [], committed: false });
          throw new Error(detail.message || "匯入失敗");
        }
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      const result = await res.json();
      setImpResult(result);
      setImpPassword("");
    } catch (e: any) {
      setImpError(e.message);
    } finally {
      setImpLoading(false);
    }
  };

  const canImport = impResult && impResult.errors.length === 0 && impMode !== "dry_run";

  return (
    <>
      <div className="mb-6">
        <p className="text-sm text-ink-3">匯出各資料表為 CSV 格式（含所有欄位），或上傳 CSV 進行資料匯入。</p>
      </div>

      {/* Export section */}
      <div className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">📥 資料匯出</h2>
        {loading ? (
          <div className="py-8 text-center text-ink-3">載入中...</div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {tables.map((t) => (
              <div key={t.key} className="flex items-center justify-between rounded-lg border border-line bg-white px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-ink">{t.label}</p>
                  <p className="text-xs text-ink-3">{t.key}.csv</p>
                </div>
                <button
                  onClick={() => handleDownload(t)}
                  disabled={downloading === t.key}
                  className="rounded-lg border border-line-2 px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-surface-2 disabled:opacity-50"
                >
                  {downloading === t.key ? "下載中..." : "下載 CSV"}
                </button>
              </div>
            ))}
          </div>
        )}
        <button
          onClick={async () => {
            for (const t of tables) {
              await exportCsv(t.endpoint, token, `${t.key}.csv`);
              await new Promise((r) => setTimeout(r, 300));
            }
          }}
          className="mt-4 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface hover:bg-ink-2"
        >
          全部下載
        </button>
      </div>

      {/* Import section */}
      <div>
        <h2 className="mb-4 text-lg font-semibold">📤 資料匯入</h2>
        <div className="rounded-lg border border-line bg-white p-6">
          {/* Step 1: Table */}
          <div className="mb-4">
            <label className="mb-1 block text-xs font-semibold text-ink-2">① 選擇資料表</label>
            <select
              value={impTable}
              onChange={(e) => { setImpTable(e.target.value); setImpResult(null); setImpError(null); }}
              className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
            >
              {IMPORT_TABLES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Step 2: Mode */}
          <div className="mb-4">
            <label className="mb-2 block text-xs font-semibold text-ink-2">② 匯入模式</label>
            <div className="flex flex-col gap-2">
              {[
                { value: "dry_run", icon: "🔍", label: "除錯模式（只驗證，不寫入資料庫）", desc: "安全，無副作用", cls: "border-accent/40 bg-accent-soft text-accent" },
                { value: "supplement", icon: "➕", label: "補登（只新增不存在的記錄）", desc: "跳過 ID 已存在的列", cls: "border-st-done/30 bg-st-done-bg" },
                { value: "clean", icon: "⚠️", label: "清洗覆蓋（更新現有 + 新增）", desc: "高風險，需輸入管理員密碼", cls: "border-st-warn/30 bg-st-warn-bg" },
              ].map((m) => (
                <label
                  key={m.value}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${impMode === m.value ? m.cls : "border-line bg-surface-2"}`}
                >
                  <input
                    type="radio"
                    name="impMode"
                    value={m.value}
                    checked={impMode === m.value}
                    onChange={() => { setImpMode(m.value as any); setImpResult(null); setImpError(null); }}
                    className="mt-0.5"
                  />
                  <div>
                    <span className="text-sm font-medium">{m.icon} {m.label}</span>
                    <p className="text-xs text-ink-3">{m.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Step 3: File */}
          <div className="mb-4">
            <label className="mb-1 block text-xs font-semibold text-ink-2">③ 上傳 CSV 檔案</label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => { setImpFile(e.target.files?.[0] ?? null); setImpResult(null); setImpError(null); }}
              className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
            />
            {impFile && <p className="mt-1 text-xs text-ink-3">已選擇：{impFile.name}（{(impFile.size / 1024).toFixed(1)} KB）</p>}
          </div>

          {/* Step 4: Password (clean only) */}
          {impMode === "clean" && (
            <div className="mb-4 rounded-lg border border-st-warn/30 bg-st-warn-bg p-4">
              <label className="mb-1 block text-xs font-semibold text-st-warn">④ 管理員密碼確認 <span className="text-st-danger">*</span></label>
              <input
                type="password"
                value={impPassword}
                onChange={(e) => setImpPassword(e.target.value)}
                placeholder="請輸入您的管理員密碼"
                className="w-full rounded-lg border border-st-warn/30 bg-white px-3 py-2 text-sm"
              />
              <p className="mt-1 text-xs text-st-warn">清洗模式將更新現有記錄，所有變更將記錄於稽核日誌</p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handlePreview}
              disabled={!impFile || impLoading}
              className="rounded-lg border border-accent/40 bg-accent-soft px-4 py-2 text-sm font-medium text-accent hover:bg-accent/15 disabled:opacity-50"
            >
              {impLoading ? "處理中..." : "🔍 執行預覽（Dry Run）"}
            </button>
            {canImport && (
              <button
                onClick={handleImport}
                disabled={impLoading}
                className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${impMode === "clean" ? "bg-st-danger hover:bg-st-danger/90" : "bg-accent hover:bg-st-active"}`}
              >
                {impLoading ? "匯入中..." : `確認匯入（${impMode === "supplement" ? "補登" : "清洗覆蓋"}）`}
              </button>
            )}
            {impResult && impResult.errors.length > 0 && impMode !== "dry_run" && (
              <p className="text-xs text-st-danger">⛔ 請先修正 {impResult.errors.length} 個錯誤後才能執行匯入</p>
            )}
          </div>

          {/* Error message */}
          {impError && (
            <div className="mt-3 rounded-lg bg-st-danger-bg p-3 text-sm text-st-danger">{impError}</div>
          )}

          {/* Preview result panel */}
          {impResult && (
            <div className="mt-5 rounded-lg border border-line bg-surface-2">
              {/* Summary */}
              <div className={`rounded-t-lg px-4 py-3 ${impResult.committed ? "bg-st-done-bg border-b border-st-done/30" : "bg-white border-b border-line"}`}>
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  {impResult.committed && <span className="font-semibold text-st-done">✅ 匯入完成</span>}
                  {!impResult.committed && <span className="font-semibold text-ink-2">預覽結果</span>}
                  <span className="text-ink-2">共 <strong>{impResult.total_rows}</strong> 列</span>
                  {impResult.would_insert > 0 && <span className="text-st-done">新增 <strong>{impResult.would_insert}</strong></span>}
                  {impResult.would_update > 0 && <span className="text-accent">更新 <strong>{impResult.would_update}</strong></span>}
                  {impResult.would_skip > 0 && <span className="text-ink-3">跳過 <strong>{impResult.would_skip}</strong></span>}
                  {impResult.errors.length > 0 && <span className="text-st-danger font-semibold">❌ {impResult.errors.length} 個錯誤</span>}
                  {impResult.warnings.length > 0 && <span className="text-st-warn">⚠️ {impResult.warnings.length} 個警告</span>}
                  {impResult.errors.length === 0 && impResult.mode === "dry_run" && (
                    <span className="text-accent">✅ 驗證通過，可切換至補登或清洗模式執行匯入</span>
                  )}
                </div>
              </div>

              {/* Errors */}
              {impResult.errors.length > 0 && (
                <div className="border-b border-line">
                  <button
                    onClick={() => setShowErrors((v) => !v)}
                    className="flex w-full items-center justify-between px-4 py-2 text-left text-sm font-medium text-st-danger hover:bg-st-danger-bg"
                  >
                    <span>❌ 錯誤列表（{impResult.errors.length} 個）</span>
                    <span>{showErrors ? "▲" : "▼"}</span>
                  </button>
                  {showErrors && (
                    <div className="max-h-60 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-st-danger-bg text-st-danger">
                          <tr>
                            <th className="px-3 py-1.5 text-left">列</th>
                            <th className="px-3 py-1.5 text-left">欄位</th>
                            <th className="px-3 py-1.5 text-left">值</th>
                            <th className="px-3 py-1.5 text-left">錯誤訊息</th>
                          </tr>
                        </thead>
                        <tbody>
                          {impResult.errors.map((e, i) => (
                            <tr key={i} className="border-t border-st-danger/30">
                              <td className="px-3 py-1 text-st-danger">第 {e.row} 列</td>
                              <td className="px-3 py-1 font-mono">{e.field}</td>
                              <td className="px-3 py-1 text-ink-3">{e.value ?? ""}</td>
                              <td className="px-3 py-1">{e.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Warnings */}
              {impResult.warnings.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowWarnings((v) => !v)}
                    className="flex w-full items-center justify-between px-4 py-2 text-left text-sm font-medium text-st-warn hover:bg-st-warn-bg"
                  >
                    <span>⚠️ 警告列表（{impResult.warnings.length} 個）</span>
                    <span>{showWarnings ? "▲" : "▼"}</span>
                  </button>
                  {showWarnings && (
                    <div className="max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-st-warn-bg text-st-warn">
                          <tr>
                            <th className="px-3 py-1.5 text-left">列</th>
                            <th className="px-3 py-1.5 text-left">欄位</th>
                            <th className="px-3 py-1.5 text-left">警告訊息</th>
                          </tr>
                        </thead>
                        <tbody>
                          {impResult.warnings.map((w, i) => (
                            <tr key={i} className="border-t border-st-warn/30">
                              <td className="px-3 py-1 text-st-warn">第 {w.row} 列</td>
                              <td className="px-3 py-1 font-mono">{w.field}</td>
                              <td className="px-3 py-1">{w.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Usage note */}
        <div className="mt-4 rounded-lg bg-accent-soft text-accent p-4 text-xs">
          <p className="font-semibold mb-1">💡 使用說明</p>
          <ul className="list-disc pl-4 space-y-1">
            <li>CSV 格式需與匯出格式相符（可先匯出後修改再匯入）</li>
            <li>CSV 必須含 <code className="bg-accent/15 px-1 rounded">id</code> 欄位；<strong>除錯模式</strong>可先驗證格式與資料正確性</li>
            <li><strong>補登</strong>：只新增 id 不存在的記錄，已存在的記錄不動</li>
            <li><strong>清洗覆蓋</strong>：依 id 更新現有記錄 + 新增不存在的記錄，所有更新會記錄到稽核日誌</li>
            <li>有驗證錯誤的列一律跳過（不寫入），警告不影響匯入</li>
          </ul>
        </div>
      </div>
    </>
  );
}
