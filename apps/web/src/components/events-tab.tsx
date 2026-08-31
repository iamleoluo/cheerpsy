"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import { money, todayISO } from "@/lib/format";

interface Room {
  id: number;
  room_code: string;
}
interface Person {
  id: number;
  name: string;
}

const BORROWER_TYPES: [string, string][] = [
  ["therapist", "心理師"],
  ["staff", "行政"],
  ["external", "外部講師"],
];

/** 5F 雲燈教室：活動 / 講座 / 場地借用 */
export function EventsTab({
  token,
  rooms,
  people,
}: {
  token: string;
  rooms: Room[];
  people: Person[];
}) {
  const [events, setEvents] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({
    name: "",
    speaker: "",
    room_id: 0,
    date: todayISO(),
    start: "14:00",
    end: "16:00",
    setup_start: "",
    borrower_type: "external",
    borrower_user_id: 0,
    borrower_name: "",
    note: "",
    has_lecture_fee: false,
    rate: "",
    hours: "",
  });
  const set = (k: string, v: any) => setF((s) => ({ ...s, [k]: v }));

  const load = useCallback(async () => {
    try {
      setEvents(await clientFetch("/events", token));
    } catch (e: any) {
      setErr(e.message);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    setOk(null);
    const iso = (t: string) => f.date + "T" + t + ":00+08:00";
    try {
      await clientFetch("/events", token, {
        method: "POST",
        body: JSON.stringify({
          name: f.name,
          speaker: f.speaker || null,
          room_id: f.room_id || null,
          start_at: iso(f.start),
          end_at: iso(f.end),
          setup_start_at: f.setup_start ? iso(f.setup_start) : null,
          setup_end_at: f.setup_start ? iso(f.start) : null,
          borrower_type: f.borrower_type,
          borrower_user_id: f.borrower_type === "external" ? null : f.borrower_user_id || null,
          borrower_name: f.borrower_type === "external" ? f.borrower_name : null,
          note: f.note || null,
          has_lecture_fee: f.has_lecture_fee,
          lecture_hourly_rate: f.has_lecture_fee ? Number(f.rate) : null,
          lecture_hours: f.has_lecture_fee ? Number(f.hours) : null,
        }),
      });
      setOk("活動已建立");
      setF({ ...f, name: "", speaker: "", note: "" });
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number, name: string) {
    if (!confirm("刪除活動「" + name + "」？")) return;
    try {
      await clientFetch("/events/" + id, token, { method: "DELETE" });
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <form onSubmit={submit} className="rounded-xl border border-gray-200 bg-white p-4">
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        {ok && <div className="mb-3 rounded bg-green-50 px-3 py-2 text-sm text-green-700">{ok}</div>}
        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">活動／講座名稱 *</span>
            <input required value={f.name} onChange={(e) => set("name", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">講師／主講人</span>
            <input value={f.speaker} onChange={(e) => set("speaker", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">使用空間</span>
            <select value={f.room_id} onChange={(e) => set("room_id", Number(e.target.value))} className="w-full rounded-lg border border-gray-300 px-3 py-2">
              <option value={0}>不佔用空間</option>
              {rooms.map((r) => (
                <option key={r.id} value={r.id}>{r.room_code}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">活動日期 *</span>
            <input required type="date" value={f.date} onChange={(e) => set("date", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
          </label>
          <div className="text-sm">
            <span className="mb-1 block text-gray-600">活動時間 *</span>
            <div className="flex items-center gap-1">
              <input required type="time" value={f.start} onChange={(e) => set("start", e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-2" />
              <span className="text-gray-400">–</span>
              <input required type="time" value={f.end} onChange={(e) => set("end", e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-2" />
            </div>
          </div>
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">場佈開始時間（留空＝不需場佈）</span>
            <input type="time" value={f.setup_start} onChange={(e) => set("setup_start", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
            <span className="mt-1 block text-xs text-gray-400">
              場佈時間會一併佔用空間，衝突檢查含此區間。
            </span>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">借用人 *</span>
            <select value={f.borrower_type} onChange={(e) => set("borrower_type", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
              {BORROWER_TYPES.map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          {f.borrower_type === "external" ? (
            <label className="text-sm">
              <span className="mb-1 block text-gray-600">借用人姓名 *</span>
              <input required value={f.borrower_name} onChange={(e) => set("borrower_name", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
            </label>
          ) : (
            <label className="text-sm">
              <span className="mb-1 block text-gray-600">人員 *</span>
              <select required value={f.borrower_user_id} onChange={(e) => set("borrower_user_id", Number(e.target.value))} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                <option value={0}>請選擇</option>
                {people.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
          )}
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">備註</span>
            <textarea rows={2} value={f.note} onChange={(e) => set("note", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
          </label>

          <div className="col-span-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={f.has_lecture_fee} onChange={(e) => set("has_lecture_fee", e.target.checked)} />
              有講師費
            </label>
            {f.has_lecture_fee && (
              <div className="mt-2 flex gap-2">
                <input type="number" min="0" value={f.rate} onChange={(e) => set("rate", e.target.value)} placeholder="鐘點費" className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm tabular-nums" />
                <input type="number" min="0" step="0.5" value={f.hours} onChange={(e) => set("hours", e.target.value)} placeholder="時數" className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm tabular-nums" />
                <span className="shrink-0 self-center text-sm tabular-nums">
                  = {money((Number(f.rate) || 0) * (Number(f.hours) || 0))}
                </span>
              </div>
            )}
            <p className="mt-2 text-xs text-amber-800">
              ⚠️ 講師費目前<b>只登錄不入帳</b>。「講師費是否入慈恩帳戶」與「講座是否酌收
              行政服務費」的規則尚未定案（open_questions Q16／Q17），因此這筆金額
              <b>不會進入月報表與心理師酬勞</b>。
            </p>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button type="submit" disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {saving ? "建立中..." : "建立活動"}
          </button>
        </div>
      </form>

      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium">活動列表</h2>
        {events.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-400">尚無活動</p>
        ) : (
          <div className="space-y-2">
            {events.map((e) => (
              <div key={e.id} className="rounded-lg border border-gray-200 p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium">{e.name}</span>
                  <button onClick={() => remove(e.id, e.name)} className="shrink-0 text-xs text-red-500 hover:underline">
                    刪除
                  </button>
                </div>
                <div className="mt-0.5 text-xs text-gray-500">
                  {e.start_at?.slice(0, 16).replace("T", " ")} – {e.end_at?.slice(11, 16)}
                  {e.room_name ? " · " + e.room_name : ""}
                  {e.setup_start_at ? " · 場佈 " + e.setup_start_at.slice(11, 16) + " 起" : ""}
                </div>
                <div className="mt-0.5 text-xs text-gray-500">
                  {e.borrower_type_label}：{e.borrower_name ?? "—"}
                  {e.speaker ? " · 講師 " + e.speaker : ""}
                </div>
                {e.has_lecture_fee && (
                  <div className="mt-1 text-xs text-amber-700">
                    講師費 {money(e.lecture_total)}（{money(e.lecture_hourly_rate)} × {e.lecture_hours} 小時）· 未入帳
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
