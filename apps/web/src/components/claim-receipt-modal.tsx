"use client";

import { useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import { money, todayISO } from "@/lib/format";

const TAX_RATE = 0.1;

/** 確認收款：所得稅 10%、轉帳手續費、實際入帳金額 */
export function ReceiptModal({
  token,
  batch,
  onClose,
  onDone,
}: {
  token: string;
  batch: { id: number; batch_number: string; applied_amount: number | null };
  onClose: () => void;
  onDone: () => void;
}) {
  const applied = batch.applied_amount ?? 0;
  const [date, setDate] = useState(todayISO());
  const [amount, setAmount] = useState(String(applied || ""));
  const [tax, setTax] = useState(false);
  const [fee, setFee] = useState("0");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const calc = useMemo(() => {
    const received = Number(amount) || 0;
    const taxAmt = tax ? Math.round(received * TAX_RATE * 100) / 100 : 0;
    const feeAmt = Number(fee) || 0;
    return { received, taxAmt, feeAmt, net: received - taxAmt - feeAmt, diff: applied - received };
  }, [amount, tax, fee, applied]);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await clientFetch(`/claim-batches/${batch.id}/confirm-receipt`, token, {
        method: "POST",
        body: JSON.stringify({
          received_date: date,
          received_amount: calc.received,
          tax_withheld: tax,
          transfer_fee: calc.feeAmt,
        }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form onSubmit={go} className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">確認收款 — {batch.batch_number}</h2>
        <p className="mb-4 text-sm text-gray-500">
          申請金額 <b>{money(applied)}</b>。確認後此核銷案會歸入
          <b>機構清冊結案表並鎖定</b>，要修改需向上一層權限解鎖。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">收款日期 *</span>
            <input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">收款金額 *</span>
            <input required type="number" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
          </label>
          <label className="col-span-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={tax} onChange={(e) => setTax(e.target.checked)} />
            扣除所得稅 10%
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">轉帳手續費</span>
            <input type="number" min="0" value={fee} onChange={(e) => setFee(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
          </label>
        </div>

        <div className="mt-4 rounded-lg bg-gray-50 p-3 text-sm">
          <div className="flex justify-between"><span>收款金額</span><span className="tabular-nums">{money(calc.received)}</span></div>
          {tax && (
            <div className="flex justify-between text-gray-600">
              <span>− 所得稅 10%</span><span className="tabular-nums">−{money(calc.taxAmt)}</span>
            </div>
          )}
          {calc.feeAmt > 0 && (
            <div className="flex justify-between text-gray-600">
              <span>− 轉帳手續費</span><span className="tabular-nums">−{money(calc.feeAmt)}</span>
            </div>
          )}
          <div className="mt-1 flex justify-between border-t border-gray-200 pt-1 font-semibold">
            <span>實際入帳金額</span><span className="tabular-nums">{money(calc.net)}</span>
          </div>
        </div>

        {Math.abs(calc.diff) > 0.01 && (
          <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            ⚠️ 收款金額與申請金額差 {money(Math.abs(calc.diff))}
            （{calc.diff > 0 ? "短收" : "溢收"}）。請確認是否相符再送出。
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
          <button type="submit" disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {saving ? "處理中..." : "確認收款並鎖定"}
          </button>
        </div>
      </form>
    </div>
  );
}

/** 送出核銷前的漏單提醒 */
export function PreSubmitModal({
  token,
  batchId,
  onClose,
  onDone,
}: {
  token: string;
  batchId: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    clientFetch(`/claim-batches/${batchId}/pre-submit-check`, token)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setErr(e.message));
    return () => {
      alive = false;
    };
  }, [token, batchId]);

  async function submit() {
    setSaving(true);
    setErr(null);
    try {
      await clientFetch(`/claim-batches/${batchId}/submit-claim`, token, {
        method: "POST",
        body: JSON.stringify({ acknowledged_missing: true }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">送出核銷前確認</h2>
        {!data ? (
          <p className="py-6 text-sm text-gray-400">檢查中...</p>
        ) : (
          <>
            <p className="mb-4 text-sm text-gray-500">
              申請金額 <b>{money(data.applied_amount)}</b>。送出後才會寫入最終期間，
              並把核銷登記時數轉出。
            </p>
            {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

            {data.missing_count > 0 ? (
              <>
                <div className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  ⚠️ 有 <b>{data.missing_count}</b> 筆符合此方案與區間的紀錄
                  <b>未納入任何核銷案</b>。請確認這幾筆是「下個月才要核銷」還是「真的遺漏」。
                </div>
                <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-200">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-left text-gray-500">
                      <tr>
                        <th className="px-2 py-1.5">日期</th>
                        <th className="px-2 py-1.5">個案</th>
                        <th className="px-2 py-1.5">心理師</th>
                        <th className="px-2 py-1.5 text-right">機構請款額</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.missing_records.map((r: any) => (
                        <tr key={r.id} className="border-t border-gray-100">
                          <td className="px-2 py-1.5">{r.session_date}</td>
                          <td className="px-2 py-1.5">{r.case_name}</td>
                          <td className="px-2 py-1.5">{r.therapist_name}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">
                            {money(r.institution_claim_amount)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
                ✓ 沒有遺漏的紀錄。
              </div>
            )}

            <div className="mt-6 flex justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">
                返回調整
              </button>
              <button
                onClick={submit}
                disabled={saving}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {saving ? "送出中..." : data.missing_count > 0 ? "已確認，仍要送出" : "送出核銷"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
