"use client";

import { money } from "@/lib/format";

export interface RateItem {
  id?: number;
  label: string;
  service_type: string | null;
  duration_minutes: number | null;
  session_seq_from: number | null;
  session_seq_to: number | null;
  total_amount: number;
  self_pay_amount: number;
  self_pay_receipt_item: string | null;
  institution_receipt_item: string | null;
  claim_hours: number | null;
  claim_unit_rate: number | null;
  is_no_show_fee: boolean;
  note: string | null;
}

export const SERVICE_TYPES: [string, string][] = [
  ["", "不限"],
  ["individual", "個別諮商"],
  ["couple", "伴侶諮商"],
  ["visitation", "會面交往"],
  ["family_group", "親子／團體"],
  ["outreach_individual", "外展個別"],
  ["outreach_group", "外展團體"],
  ["lecture", "講座／活動"],
];

export const emptyRateItem = (): RateItem => ({
  label: "",
  service_type: null,
  duration_minutes: null,
  session_seq_from: null,
  session_seq_to: null,
  total_amount: 0,
  self_pay_amount: 0,
  self_pay_receipt_item: null,
  institution_receipt_item: null,
  claim_hours: null,
  claim_unit_rate: null,
  is_no_show_fee: false,
  note: null,
});

/** 快速範本。慈恩定案：服務型態不同要**拆成不同方案**，
 *  因此這裡只保留「第幾次階梯」這種必須放在同一方案內的樣態。 */
const PRESETS: { name: string; hint: string; make: () => RateItem[] }[] = [
  {
    name: "單一價格",
    hint: "多數方案。一個方案一種價格",
    make: () => [{ ...emptyRateItem(), label: "諮商費用" }],
  },
  {
    name: "依次數階梯",
    hint: "如衛生局市民第1次免費第2次$200、蛹之生第3次起漲價",
    make: () => [
      { ...emptyRateItem(), label: "第 1 次", session_seq_from: 1, session_seq_to: 1 },
      { ...emptyRateItem(), label: "第 2 次", session_seq_from: 2, session_seq_to: 2 },
      { ...emptyRateItem(), label: "第 3 次起", session_seq_from: 3, session_seq_to: null },
    ],
  },
  {
    name: "爽約費",
    hint: "如南家扶無事先請假 $200",
    make: () => [{ ...emptyRateItem(), label: "無事先請假爽約費", is_no_show_fee: true }],
  },
];

function num(v: string): number | null {
  return v === "" ? null : Number(v);
}

export function RateItemsEditor({
  items,
  onChange,
  disabled,
}: {
  items: RateItem[];
  onChange: (items: RateItem[]) => void;
  disabled?: boolean;
}) {
  const upd = (i: number, patch: Partial<RateItem>) => {
    const next = [...items];
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">方案價目</span>
        <span className="text-xs text-gray-500">
          原則上<b>一個方案一種價格</b>；只有「第幾次不同價」要放在同一方案內
        </span>
        {!disabled && (
          <div className="ml-auto flex flex-wrap gap-1">
            {PRESETS.map((p) => (
              <button
                key={p.name}
                type="button"
                onClick={() => onChange([...items, ...p.make()])}
                title={p.hint}
                className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
              >
                ＋{p.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {items.length === 0 && (
        <p className="rounded-lg border border-dashed border-gray-300 px-3 py-6 text-center text-sm text-gray-400">
          尚未設定價目。合約固定價的方案至少需要一筆。
        </p>
      )}

      <div className="space-y-2">
        {items.map((r, i) => {
          const inst = (Number(r.total_amount) || 0) - (Number(r.self_pay_amount) || 0);
          const bad = inst < 0;
          return (
            <div
              key={i}
              className={`rounded-lg border p-3 ${r.is_no_show_fee ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-white"}`}
            >
              <div className="mb-2 flex items-center gap-2">
                <input
                  required
                  disabled={disabled}
                  value={r.label}
                  onChange={(e) => upd(i, { label: e.target.value })}
                  placeholder="項目名稱，如「個別諮商」"
                  className="flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm font-medium"
                />
                <label className="flex shrink-0 items-center gap-1 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={r.is_no_show_fee}
                    onChange={(e) => upd(i, { is_no_show_fee: e.target.checked })}
                  />
                  爽約費
                </label>
                {!disabled && (
                  <button
                    type="button"
                    onClick={() => onChange(items.filter((_, j) => j !== i))}
                    className="shrink-0 text-xs text-red-500 hover:underline"
                  >
                    移除
                  </button>
                )}
              </div>

              {!r.is_no_show_fee && (
                <div className="mb-2 grid grid-cols-2 gap-2 md:grid-cols-4">
                  <label className="text-xs md:col-span-2">
                    <span className="mb-0.5 block text-gray-500">
                      適用服務型態
                      <span className="ml-1 text-gray-400">（通常留「不限」，改用拆方案）</span>
                    </span>
                    <select
                      disabled={disabled}
                      value={r.service_type ?? ""}
                      onChange={(e) => upd(i, { service_type: e.target.value || null })}
                      className="w-full rounded-lg border border-gray-300 px-2 py-1.5"
                    >
                      {SERVICE_TYPES.map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs">
                    <span className="mb-0.5 block text-gray-500">時長（分鐘）</span>
                    <input
                      type="number"
                      min="0"
                      disabled={disabled}
                      value={r.duration_minutes ?? ""}
                      onChange={(e) => upd(i, { duration_minutes: num(e.target.value) })}
                      placeholder="不限"
                      className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                    />
                  </label>
                  <label className="text-xs">
                    <span className="mb-0.5 block text-gray-500">適用第幾次（起）</span>
                    <input
                      type="number"
                      min="1"
                      disabled={disabled}
                      value={r.session_seq_from ?? ""}
                      onChange={(e) => upd(i, { session_seq_from: num(e.target.value) })}
                      placeholder="不限"
                      className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                    />
                  </label>
                  <label className="text-xs">
                    <span className="mb-0.5 block text-gray-500">至第幾次（迄）</span>
                    <input
                      type="number"
                      min="1"
                      disabled={disabled}
                      value={r.session_seq_to ?? ""}
                      onChange={(e) => upd(i, { session_seq_to: num(e.target.value) })}
                      placeholder="以後皆同"
                      className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                    />
                  </label>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <label className="text-xs">
                  <span className="mb-0.5 block text-gray-500">
                    {r.is_no_show_fee ? "爽約費金額 *" : "總額 *"}
                  </span>
                  <input
                    required
                    type="number"
                    min="0"
                    disabled={disabled}
                    value={r.total_amount}
                    onChange={(e) => upd(i, { total_amount: Number(e.target.value) })}
                    className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                  />
                </label>
                {!r.is_no_show_fee && (
                  <>
                    <label className="text-xs">
                      <span className="mb-0.5 block text-gray-500">個案自付額</span>
                      <input
                        type="number"
                        min="0"
                        disabled={disabled}
                        value={r.self_pay_amount}
                        onChange={(e) => upd(i, { self_pay_amount: Number(e.target.value) })}
                        className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                      />
                    </label>
                    <div className="col-span-2 self-end text-xs">
                      <span className="text-gray-500">機構請款額 </span>
                      <b className={bad ? "text-red-600" : ""}>{money(inst)}</b>
                      {bad && <span className="ml-1 text-red-600">自付額不可高於總額</span>}
                      {inst > 0 && (Number(r.self_pay_amount) || 0) > 0 && (
                        <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-violet-700">
                          雙源分攤
                        </span>
                      )}
                    </div>
                  </>
                )}
              </div>

              {!r.is_no_show_fee && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-gray-500">
                    收據品項與核銷登記時數（選填）
                  </summary>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <label className="text-xs">
                      <span className="mb-0.5 block text-gray-500">個案端收據品項</span>
                      <input
                        disabled={disabled}
                        value={r.self_pay_receipt_item ?? ""}
                        onChange={(e) => upd(i, { self_pay_receipt_item: e.target.value || null })}
                        placeholder="如 行政規費／場地費"
                        className="w-full rounded-lg border border-gray-300 px-2 py-1.5"
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-0.5 block text-gray-500">機構端收據品項</span>
                      <input
                        disabled={disabled}
                        value={r.institution_receipt_item ?? ""}
                        onChange={(e) => upd(i, { institution_receipt_item: e.target.value || null })}
                        placeholder="如 諮商鐘點費"
                        className="w-full rounded-lg border border-gray-300 px-2 py-1.5"
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-0.5 block text-gray-500">核銷單登記時數</span>
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        disabled={disabled}
                        value={r.claim_hours ?? ""}
                        onChange={(e) => upd(i, { claim_hours: num(e.target.value) })}
                        placeholder="同實際時數"
                        className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-0.5 block text-gray-500">核銷單登記單價</span>
                      <input
                        type="number"
                        min="0"
                        disabled={disabled}
                        value={r.claim_unit_rate ?? ""}
                        onChange={(e) => upd(i, { claim_unit_rate: num(e.target.value) })}
                        placeholder="同實際單價"
                        className="w-full rounded-lg border border-gray-300 px-2 py-1.5 tabular-nums"
                      />
                    </label>
                    <label className="col-span-2 text-xs">
                      <span className="mb-0.5 block text-gray-500">備註</span>
                      <input
                        disabled={disabled}
                        value={r.note ?? ""}
                        onChange={(e) => upd(i, { note: e.target.value || null })}
                        className="w-full rounded-lg border border-gray-300 px-2 py-1.5"
                      />
                    </label>
                  </div>
                  {(r.claim_hours != null || r.claim_unit_rate != null) && (
                    <p className="mt-1.5 rounded bg-blue-50 px-2 py-1.5 text-xs text-blue-800">
                      機構預算科目單價固定時，用時數湊出實際金額。
                      登記 {r.claim_hours ?? "?"} 小時 × {money(r.claim_unit_rate ?? 0)} ={" "}
                      {money((Number(r.claim_hours) || 0) * (Number(r.claim_unit_rate) || 0))}
                      ，實際機構請款額 {money(inst)}。兩者不必相等。
                    </p>
                  )}
                </details>
              )}
            </div>
          );
        })}
      </div>

      {!disabled && (
        <button
          type="button"
          onClick={() => onChange([...items, emptyRateItem()])}
          className="mt-2 w-full rounded-lg border border-dashed border-gray-300 py-2 text-sm text-gray-500 hover:bg-gray-50"
        >
          ＋ 新增一筆價目
        </button>
      )}
    </div>
  );
}

/** 列表用的價目摘要 */
export function RateSummary({ items }: { items: RateItem[] }) {
  const normal = items.filter((r) => !r.is_no_show_fee);
  const noShow = items.find((r) => r.is_no_show_fee);
  if (normal.length === 0) return <span className="text-gray-400">未設定價目</span>;
  return (
    <span>
      {normal.slice(0, 3).map((r, i) => (
        <span key={i}>
          {i > 0 && "／"}
          {r.label} {money(r.total_amount)}
          {r.self_pay_amount > 0 && <span className="text-gray-400">（自付 {money(r.self_pay_amount)}）</span>}
        </span>
      ))}
      {normal.length > 3 && <span className="text-gray-400">…共 {normal.length} 項</span>}
      {noShow && <span className="ml-1 text-amber-600">· 爽約費 {money(noShow.total_amount)}</span>}
    </span>
  );
}
