"use client";

import { useMemo } from "react";
import { Button, Select, Input } from "@/components/ui";

/**
 * 費率規則編輯器 — V2升級計畫 09 §3.5 的最後一個共用區塊，也是唯一沒有參考
 * 畫面的一個（原型沒有這一頁，診所現在是用 Excel 對照表人工查價）。
 *
 * 所以形狀是從**規則引擎的語意**倒推出來的，而不是照著誰的畫面畫：
 *
 *   ① 有序、先匹配先贏 → 順序必須看得見、改得動，而不是一個數字欄位。
 *      「其餘情況」（空條件）排在中間會讓它後面的規則永遠輪不到，
 *      那是編輯時最容易犯、也最難自己發現的錯，所以就地標紅。
 *   ② 一條規則可以有**多個**條件（when 是字典不是單值）。舊的建立方案表單
 *      只讓選一個 visit_seq，於是家防中心那種「個別$2000／親職$1000／
 *      家族$2400」根本填不進去——consult_type 這個維度在 UI 上不存在。
 *   ③ 條件鍵一律從下拉選，不讓人手打。pricing.rule_matches 對不認得的鍵是
 *      **寬容跳過**，`sesion_type`（少一個 s）會變成一條命中全部的規則，
 *      而且悄悄地。後端會擋，但最好的擋法是打不出那個字。
 *
 * 這支只管「編輯出一份合法的規則清單」，不負責存檔——呼叫端決定要送去建立
 * 新方案（POST /institution/plans）還是取代既有方案（PUT .../rate-rules）。
 */

/* ── 條件維度 ──────────────────────────────────────────────────────────
 * key 必須與後端 pricing.CONDITION_KEYS 一致。少了一個只是選單裡看不到；
 * 多了一個會在存檔時被後端擋下來（而不是靜靜變成 catch-all）。
 */
type Dim = {
  key: string;
  label: string;
  hint?: string;
  kind: "enum" | "number" | "text";
  options?: { value: string; label: string }[];
};

export const RATE_DIMENSIONS: Dim[] = [
  {
    key: "consult_type",
    label: "諮商型態",
    hint: "個別／親職／家族……這是計價維度，跟「型式」是不同軸",
    kind: "enum",
    options: [
      { value: "individual", label: "個別" },
      { value: "couple", label: "伴侶" },
      { value: "family", label: "家族" },
      { value: "parenting", label: "親職" },
      { value: "group", label: "團體" },
      { value: "lecture", label: "講座" },
      { value: "meeting", label: "會議" },
    ],
  },
  {
    key: "session_type",
    label: "型式",
    hint: "現場／視訊／外展，決定要不要診間、要不要外出保底",
    kind: "enum",
    options: [
      { value: "in_person", label: "現場" },
      { value: "online", label: "視訊" },
      { value: "outdoor", label: "外展" },
    ],
  },
  { key: "visit_seq", label: "第幾次", hint: "如「第一次免自付、第二次起自付 $200」", kind: "number" },
  { key: "duration_min", label: "時長（分）", kind: "number" },
  {
    key: "location_kind",
    label: "地點",
    kind: "enum",
    options: [
      { value: "clinic", label: "所內" },
      { value: "home", label: "到宅" },
      { value: "school", label: "學校" },
      { value: "other", label: "其他" },
    ],
  },
  { key: "time_band", label: "時段", hint: "如平日／假日／夜間，須與預約帶入的值一致", kind: "text" },
  { key: "sub_unit", label: "子單位", hint: "同一份合約下的分單位，如某分局、某校區", kind: "text" },
];

const DIM = Object.fromEntries(RATE_DIMENSIONS.map((d) => [d.key, d]));

/* ── 編輯中的形狀 ─────────────────────────────────────────────────────
 * 條件在 UI 上是一個陣列（好增刪、好渲染），送出前才摺成 when 字典。
 */
export type Cond = { key: string; op: "eq" | "gte" | "lte"; value: string };
export type DraftRule = {
  /** React key 用；不送後端。 */
  uid: string;
  conds: Cond[];
  price_source: "fixed" | "therapist_rate";
  unit_price: string;
  case_payable: string;
  label: string;
};

let seq = 0;
export const newRule = (): DraftRule => ({
  uid: `r${++seq}`,
  conds: [],
  price_source: "fixed",
  unit_price: "",
  case_payable: "0",
  label: "",
});

/** 後端 when 字典 → 編輯中的條件陣列。 */
export function toDraft(whenJson: string, r: {
  price_source?: string; unit_price?: number | null; case_payable?: number | null; label?: string | null;
}): DraftRule {
  let when: Record<string, unknown> = {};
  try {
    when = JSON.parse(whenJson || "{}");
  } catch {
    when = {};
  }
  const conds: Cond[] = Object.entries(when).map(([key, raw]) => {
    if (raw && typeof raw === "object") {
      const [op, v] = Object.entries(raw as Record<string, unknown>)[0] ?? ["eq", ""];
      return { key, op: (op === "gte" || op === "lte" ? op : "eq") as Cond["op"], value: String(v) };
    }
    return { key, op: "eq", value: String(raw) };
  });
  return {
    uid: `r${++seq}`,
    conds,
    price_source: r.price_source === "therapist_rate" ? "therapist_rate" : "fixed",
    unit_price: r.unit_price != null ? String(r.unit_price) : "",
    case_payable: r.case_payable != null ? String(r.case_payable) : "0",
    label: r.label ?? "",
  };
}

/** 編輯中的條件陣列 → 送給後端的 when 字典。 */
export function condsToWhen(conds: Cond[]): Record<string, unknown> {
  const when: Record<string, unknown> = {};
  for (const c of conds) {
    if (!c.key || c.value === "") continue;
    const d = DIM[c.key];
    const v = d?.kind === "number" ? Number(c.value) : c.value;
    when[c.key] = c.op === "eq" ? v : { [c.op]: v };
  }
  return when;
}

/** 送給 POST /plans 或 PUT /rate-rules 的形狀。順序就是陣列順序。 */
export function toPayload(rules: DraftRule[]) {
  return rules.map((r, i) => ({
    sort_order: (i + 1) * 10,
    when: condsToWhen(r.conds),
    price_source: r.price_source,
    unit_price: r.price_source === "fixed" ? Number(r.unit_price || 0) : null,
    case_payable: Number(r.case_payable || 0),
    label: r.label || null,
  }));
}

/**
 * 存檔前自己先驗一次。後端擋得更嚴（那才是真正的閘門），但錯誤在按下送出前
 * 就看得到，比送出去被打回來好——尤其「其餘情況排在中間」這種，錯誤訊息
 * 要指著那一條才有用。
 */
export function validate(rules: DraftRule[]): Record<string, string> {
  const errs: Record<string, string> = {};
  if (rules.length === 0) return { _: "至少要有一條規則，否則這個方案報不出價" };
  rules.forEach((r, i) => {
    if (r.price_source === "fixed" && r.unit_price.trim() === "") {
      errs[r.uid] = "採固定價就必須填鐘點費，留空會讓報價變 $0";
    } else if (Number(r.unit_price) < 0 || Number(r.case_payable) < 0) {
      errs[r.uid] = "金額不可為負數";
    } else if (r.conds.some((c) => c.value === "")) {
      errs[r.uid] = "有條件沒填值";
    } else if (r.conds.length === 0 && i !== rules.length - 1) {
      // 先匹配先贏——這一條之後的規則永遠輪不到
      errs[r.uid] = "這條沒有任何條件（＝其餘情況），排在它後面的規則永遠輪不到。請把它移到最後。";
    }
  });
  return errs;
}

export function RateRuleEditor({
  rules,
  onChange,
  errors,
}: {
  rules: DraftRule[];
  onChange: (next: DraftRule[]) => void;
  errors?: Record<string, string>;
}) {
  const errs = errors ?? {};
  const patch = (i: number, p: Partial<DraftRule>) =>
    onChange(rules.map((r, idx) => (idx === i ? { ...r, ...p } : r)));

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= rules.length) return;
    const next = [...rules];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  // 已經被用掉的維度不再出現在「＋條件」選單裡：同一個 key 在 when 字典裡
  // 只能有一個值，重複選只會互相覆蓋
  const available = (r: DraftRule) =>
    RATE_DIMENSIONS.filter((d) => !r.conds.some((c) => c.key === d.key));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-2">費率規則</span>
        <span className="text-[10.5px] text-ink-3">由上而下比對，第一條符合的就決定金額</span>
        <Button
          type="button"
          size="sm"
          className="ml-auto"
          onClick={() => onChange([...rules, newRule()])}
        >
          ＋ 規則
        </Button>
      </div>

      {errs._ && (
        <p className="rounded-control bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{errs._}</p>
      )}

      {rules.map((r, i) => {
        const isCatchAll = r.conds.length === 0;
        const err = errs[r.uid];
        return (
          <div
            key={r.uid}
            className={`rounded-control border p-2.5 ${
              err ? "border-st-danger/50 bg-st-danger-bg/40" : "border-line bg-surface"
            }`}
          >
            <div className="mb-2 flex items-center gap-1.5">
              <span className="ident rounded-badge bg-surface-3 px-1.5 py-px text-[10px] text-ink-2">
                {i + 1}
              </span>
              {isCatchAll ? (
                <span className="text-[11px] font-medium text-ink-2">其餘情況</span>
              ) : (
                <span className="text-[11px] text-ink-3">當以下條件全部符合</span>
              )}
              <div className="ml-auto flex items-center gap-1">
                <Button type="button" size="mini" onClick={() => move(i, -1)} disabled={i === 0} aria-label="上移">↑</Button>
                <Button type="button" size="mini" onClick={() => move(i, 1)} disabled={i === rules.length - 1} aria-label="下移">↓</Button>
                <Button
                  type="button"
                  size="mini"
                  variant="danger"
                  onClick={() => onChange(rules.filter((_, idx) => idx !== i))}
                  disabled={rules.length === 1}
                >
                  刪除
                </Button>
              </div>
            </div>

            {/* 條件 */}
            <div className="mb-2 flex flex-col gap-1.5">
              {r.conds.map((c, ci) => {
                const d = DIM[c.key];
                return (
                  <div key={ci} className="flex flex-wrap items-center gap-1.5">
                    <span className="w-16 shrink-0 text-[11px] text-ink-3">{d?.label ?? c.key}</span>
                    {d?.kind === "number" ? (
                      <>
                        <Select
                          value={c.op}
                          onChange={(e) =>
                            patch(i, {
                              conds: r.conds.map((x, xi) =>
                                xi === ci ? { ...x, op: e.target.value as Cond["op"] } : x,
                              ),
                            })
                          }
                          className="w-16"
                        >
                          <option value="eq">＝</option>
                          <option value="gte">≥</option>
                          <option value="lte">≤</option>
                        </Select>
                        <Input
                          type="number"
                          value={c.value}
                          onChange={(e) =>
                            patch(i, {
                              conds: r.conds.map((x, xi) => (xi === ci ? { ...x, value: e.target.value } : x)),
                            })
                          }
                          className="w-20"
                        />
                      </>
                    ) : d?.kind === "enum" ? (
                      <Select
                        value={c.value}
                        onChange={(e) =>
                          patch(i, {
                            conds: r.conds.map((x, xi) => (xi === ci ? { ...x, value: e.target.value } : x)),
                          })
                        }
                        className="w-32"
                      >
                        <option value="">— 請選 —</option>
                        {d.options!.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </Select>
                    ) : (
                      <Input
                        value={c.value}
                        onChange={(e) =>
                          patch(i, {
                            conds: r.conds.map((x, xi) => (xi === ci ? { ...x, value: e.target.value } : x)),
                          })
                        }
                        className="w-32"
                      />
                    )}
                    <button
                      type="button"
                      onClick={() => patch(i, { conds: r.conds.filter((_, xi) => xi !== ci) })}
                      className="text-[11px] text-ink-3 hover:text-st-danger"
                      aria-label="移除條件"
                    >
                      ✕
                    </button>
                    {d?.hint && <span className="text-[10px] text-ink-3">{d.hint}</span>}
                  </div>
                );
              })}

              {available(r).length > 0 && (
                <Select
                  value=""
                  onChange={(e) =>
                    e.target.value &&
                    patch(i, { conds: [...r.conds, { key: e.target.value, op: "eq", value: "" }] })
                  }
                  className="w-40"
                >
                  <option value="">＋ 加條件…</option>
                  {available(r).map((d) => (
                    <option key={d.key} value={d.key}>{d.label}</option>
                  ))}
                </Select>
              )}
            </div>

            {/* 金額 */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <label className="block">
                <span className="mb-0.5 block text-[10px] text-ink-3">計價方式</span>
                <Select
                  value={r.price_source}
                  onChange={(e) => patch(i, { price_source: e.target.value as DraftRule["price_source"] })}
                >
                  <option value="fixed">固定價</option>
                  <option value="therapist_rate">依心理師鐘點費</option>
                </Select>
              </label>
              <label className="block">
                <span className="mb-0.5 block text-[10px] text-ink-3">鐘點費</span>
                <Input
                  type="number"
                  value={r.price_source === "therapist_rate" ? "" : r.unit_price}
                  onChange={(e) => patch(i, { unit_price: e.target.value })}
                  disabled={r.price_source === "therapist_rate"}
                  placeholder={r.price_source === "therapist_rate" ? "取心理師主檔" : ""}
                />
              </label>
              <label className="block">
                <span className="mb-0.5 block text-[10px] text-ink-3">個案自付</span>
                <Input
                  type="number"
                  value={r.case_payable}
                  onChange={(e) => patch(i, { case_payable: e.target.value })}
                />
              </label>
              <label className="block">
                <span className="mb-0.5 block text-[10px] text-ink-3">說明</span>
                <Input
                  value={r.label}
                  onChange={(e) => patch(i, { label: e.target.value })}
                  placeholder="如「第一次免自付」"
                />
              </label>
            </div>

            {err && <p className="mt-1.5 text-[11px] text-st-danger">{err}</p>}
          </div>
        );
      })}

      <RuleSummary rules={rules} />
    </div>
  );
}

/**
 * 一句話把整份規則讀回來，因為「先匹配先贏」的結果不容易從一堆表單欄位上看出來。
 * 沒有「其餘情況」是合法的，但值得提醒：條件都沒中就報不出價。
 */
function RuleSummary({ rules }: { rules: DraftRule[] }) {
  const hasCatchAll = useMemo(() => rules.some((r) => r.conds.length === 0), [rules]);
  return (
    <p className="text-[10.5px] text-ink-3">
      共 {rules.length} 條，由上而下比對。
      {hasCatchAll ? (
        <>最後一條沒有條件，所以任何情況都報得出價。</>
      ) : (
        <span className="text-st-warn">
          沒有「其餘情況」規則——條件都沒命中時這個方案報不出價。可加一條不設條件的放在最後。
        </span>
      )}
    </p>
  );
}
