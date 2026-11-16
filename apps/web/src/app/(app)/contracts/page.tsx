"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface Institution {
  id: number;
  name: string;
}

interface Contract {
  id: number;
  institution_id: number;
  institution_name: string | null;
  name: string;
  eligibility: string | null;
  hourly_rate: number;
  self_pay_amount: number;
  institution_claim_amount: number;
  cap_type: "amount" | "count" | "unlimited";
  cap_value: number | null;
  contact_person: string | null;
  contact_phone: string | null;
  valid_from: string | null;
  valid_until: string | null;
  is_active: boolean;
  plan_count: number;
  settlement_direction: "to_clinic" | "to_therapist";
  rebate_rate: number | null;
  rebate_method: string | null;
  requires_institution_receipt: boolean;
}

const CAP_LABEL: Record<string, string> = {
  amount: "金額上限",
  count: "次數上限",
  unlimited: "不限",
};

function money(n: number) {
  return `$${n.toLocaleString()}`;
}

function capText(c: Contract) {
  if (c.cap_type === "unlimited") return "不限";
  if (c.cap_type === "amount") return money(c.cap_value ?? 0);
  return `${(c.cap_value ?? 0).toLocaleString()} 次`;
}

export default function ContractsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Contract | "new" | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [cs, insts] = await Promise.all([
        clientFetch("/institution-contracts", token),
        clientFetch("/institutions", token),
      ]);
      setContracts(cs);
      setInstitutions(insts);
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

  async function deactivate(c: Contract) {
    if (!confirm(`確定要停用合約「${c.name}」？底下的方案會一併看不到。`)) return;
    try {
      await clientFetch(`/institution-contracts/${c.id}`, token, { method: "DELETE" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">機構合約清冊</h1>
          <p className="mt-1 text-sm text-gray-500">
            合約定義錢的規則：鐘點費、個案自付額、核銷上限。下一層「機構方案清冊」再依合約開出年度方案。
          </p>
        </div>
        <button
          onClick={() => setEditing("new")}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          ＋新增機構合約
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-4 py-3">機構單位</th>
              <th className="px-4 py-3">合約 / 公告方案</th>
              <th className="px-4 py-3">方案身份條件</th>
              <th className="px-4 py-3 text-right">方案鐘點費</th>
              <th className="px-4 py-3 text-right">個案自付額</th>
              <th className="px-4 py-3 text-right">機構請款額</th>
              <th className="px-4 py-3">核銷上限</th>
              <th className="px-4 py-3">款項流向</th>
              <th className="px-4 py-3">承辦人</th>
              <th className="px-4 py-3">有效期間</th>
              <th className="px-4 py-3 text-center">方案數</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {contracts.length === 0 && (
              <tr>
                <td colSpan={12} className="px-4 py-10 text-center text-gray-400">
                  尚無合約。先在「系統管理 → 機構」建立機構單位，再回來新增合約。
                </td>
              </tr>
            )}
            {contracts.map((c) => (
              <tr key={c.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium">{c.institution_name}</td>
                <td className="px-4 py-3">{c.name}</td>
                <td className="px-4 py-3 text-gray-600">{c.eligibility || "—"}</td>
                <td className="px-4 py-3 text-right tabular-nums">{money(c.hourly_rate)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{money(c.self_pay_amount)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-gray-500">
                  {money(c.institution_claim_amount)}
                </td>
                <td className="px-4 py-3">
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                    {CAP_LABEL[c.cap_type]}
                  </span>
                  <span className="ml-1.5 tabular-nums">{capText(c)}</span>
                </td>
                <td className="px-4 py-3">
                  {c.settlement_direction === "to_therapist" ? (
                    <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-700">
                      回扣型
                      {c.rebate_rate != null ? ` · 回繳 ${Math.round(c.rebate_rate * 100)}%` : ""}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-500">匯給慈恩</span>
                  )}
                </td>
                <td className="px-4 py-3 text-gray-600">
                  {c.contact_person || "—"}
                  {c.contact_phone && (
                    <span className="block text-xs text-gray-400">{c.contact_phone}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {c.valid_from || "—"} ~ {c.valid_until || "—"}
                </td>
                <td className="px-4 py-3 text-center tabular-nums">{c.plan_count}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2 text-xs">
                    <button onClick={() => setEditing(c)} className="text-primary-600 hover:underline">
                      編輯
                    </button>
                    <button onClick={() => deactivate(c)} className="text-red-500 hover:underline">
                      停用
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        合約中途調整鐘點費時，<b>已產生的紀錄沿用建立當下的價格</b>，不回溯。調整會寫入稽核日誌。
      </p>

      {editing && (
        <ContractForm
          token={token}
          institutions={institutions}
          contract={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function ContractForm({
  token,
  institutions,
  contract,
  onClose,
  onSaved,
}: {
  token: string;
  institutions: Institution[];
  contract: Contract | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [institutionId, setInstitutionId] = useState(
    contract?.institution_id ?? institutions[0]?.id ?? 0
  );
  const [name, setName] = useState(contract?.name ?? "");
  const [eligibility, setEligibility] = useState(contract?.eligibility ?? "");
  const [hourlyRate, setHourlyRate] = useState(String(contract?.hourly_rate ?? ""));
  const [selfPay, setSelfPay] = useState(String(contract?.self_pay_amount ?? "0"));
  const [capType, setCapType] = useState(contract?.cap_type ?? "unlimited");
  const [capValue, setCapValue] = useState(
    contract?.cap_value != null ? String(contract.cap_value) : ""
  );
  const [person, setPerson] = useState(contract?.contact_person ?? "");
  const [phone, setPhone] = useState(contract?.contact_phone ?? "");
  const [direction, setDirection] = useState<"to_clinic" | "to_therapist">(
    contract?.settlement_direction ?? "to_clinic"
  );
  const [rebateRate, setRebateRate] = useState(
    contract?.rebate_rate != null ? String(Math.round(contract.rebate_rate * 100)) : ""
  );
  const [needInstReceipt, setNeedInstReceipt] = useState(
    contract?.requires_institution_receipt ?? false
  );
  const [from, setFrom] = useState(contract?.valid_from ?? "");
  const [until, setUntil] = useState(contract?.valid_until ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const rate = Number(hourlyRate) || 0;
  const pay = Number(selfPay) || 0;
  const claim = rate - pay;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const payload: any = {
      name,
      eligibility: eligibility || null,
      hourly_rate: rate,
      self_pay_amount: pay,
      cap_type: capType,
      cap_value: capType === "unlimited" ? null : Number(capValue) || 0,
      contact_person: person || null,
      contact_phone: phone || null,
      valid_from: from || null,
      valid_until: until || null,
      settlement_direction: direction,
      rebate_rate: direction === "to_therapist" && rebateRate !== "" ? Number(rebateRate) / 100 : null,
      rebate_method: direction === "to_therapist" ? "payout_deduct" : null,
      requires_institution_receipt: needInstReceipt,
    };
    try {
      if (contract) {
        await clientFetch(`/institution-contracts/${contract.id}`, token, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await clientFetch("/institution-contracts", token, {
          method: "POST",
          body: JSON.stringify({ ...payload, institution_id: institutionId }),
        });
      }
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form
        onSubmit={submit}
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="mb-4 text-lg font-bold">{contract ? "編輯機構合約" : "新增機構合約"}</h2>

        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

        <div className="grid grid-cols-2 gap-4">
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">機構單位 *</span>
            <select
              value={institutionId}
              onChange={(e) => setInstitutionId(Number(e.target.value))}
              disabled={!!contract}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 disabled:bg-gray-100"
            >
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">合約 / 公告方案 *</span>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：15-45青壯世代心理健康方案"
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">方案身份條件</span>
            <input
              value={eligibility}
              onChange={(e) => setEligibility(e.target.value)}
              placeholder="如：15-45歲民眾"
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">方案鐘點費 *（含自付額）</span>
            <input
              required
              type="number"
              min="0"
              value={hourlyRate}
              onChange={(e) => setHourlyRate(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">個案自付額</span>
            <input
              type="number"
              min="0"
              value={selfPay}
              onChange={(e) => setSelfPay(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums"
            />
          </label>

          <div className="col-span-2 rounded-lg bg-gray-50 px-3 py-2 text-sm">
            機構請款額 ＝ 鐘點費 − 自付額 ＝{" "}
            <b className={claim < 0 ? "text-red-600" : ""}>{money(claim)}</b>
            {claim < 0 && <span className="ml-2 text-xs text-red-600">自付額不可高於鐘點費</span>}
            {pay === 0 && claim >= 0 && (
              <span className="ml-2 text-xs text-gray-500">自付 $0 ＝ 機構全額</span>
            )}
          </div>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">總核銷上限</span>
            <select
              value={capType}
              onChange={(e) => setCapType(e.target.value as any)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              <option value="unlimited">不限</option>
              <option value="amount">金額上限</option>
              <option value="count">次數上限</option>
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">
              上限值{capType === "unlimited" ? "（不限時免填）" : " *"}
            </span>
            <input
              type="number"
              min="0"
              disabled={capType === "unlimited"}
              required={capType !== "unlimited"}
              value={capType === "unlimited" ? "" : capValue}
              onChange={(e) => setCapValue(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums disabled:bg-gray-100"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">合約承辦人</span>
            <input
              value={person}
              onChange={(e) => setPerson(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">聯絡電話</span>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <div className="col-span-2 rounded-lg border border-gray-200 p-3">
            <div className="mb-2 text-sm text-gray-600">款項流向</div>
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm">
                <input type="radio" className="mt-1" checked={direction === "to_clinic"} onChange={() => setDirection("to_clinic")} />
                <span>
                  <b>機構匯款給慈恩</b>
                  <span className="block text-xs text-gray-500">
                    一般情形。機構請款額會進入「應收帳冊 → 機構」等待撥款。
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input type="radio" className="mt-1" checked={direction === "to_therapist"} onChange={() => setDirection("to_therapist")} />
                <span>
                  <b>回扣型：機構直接匯款給心理師</b>
                  <span className="block text-xs text-gray-500">
                    核銷資料是「領據給心理師簽名」「心理師銀行帳戶影本」的方案屬此類。
                    慈恩對機構沒有應收，要收的是心理師依約回繳的部分。
                  </span>
                </span>
              </label>
            </div>
            {direction === "to_therapist" && (
              <div className="mt-3">
                <label className="block text-sm">
                  <span className="mb-1 block text-gray-600">回繳比例覆寫（%，留空＝依抽成計算）</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={rebateRate}
                    onChange={(e) => setRebateRate(e.target.value)}
                    placeholder="依心理師抽成自動計算"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums"
                  />
                </label>
                <p className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600">
                  回扣金額 ＝ 機構請款額 × (1 − 心理師個別抽成率)。
                  例：請款 $2,000、抽成 60% → 心理師留 $1,200，回繳慈恩 $800。
                  <b className="mt-1 block">
                    回繳方式固定為「從當月酬勞扣除」，因此不進應收帳冊，
                    在日報表確認無誤匯入月報表時算出並扣除。
                  </b>
                </p>
              </div>
            )}
          </div>

          <label className="col-span-2 flex items-start gap-2 rounded-lg border border-gray-200 p-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={needInstReceipt}
              onChange={(e) => setNeedInstReceipt(e.target.checked)}
            />
            <span>
              <b>需要開立機構收據</b>
              <span className="block text-xs text-gray-500">
                多數方案不用（衛生局市民、15-45青壯、國軍都不用），目前只有台南教支需要。
                個案自付額的收據一律照方案規定開給個案，與此項無關。
              </span>
            </span>
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">有效起日</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">有效迄日</span>
            <input
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={saving || claim < 0}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {saving ? "儲存中..." : "儲存"}
          </button>
        </div>
      </form>
    </div>
  );
}
