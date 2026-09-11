"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { CheckInPanel, RentalsTab, HallTab } from "@/features/rooms";
import type { Appointment, Room } from "@/features/rooms/types";

/**
 * GET /room-calendar 的一格 —— 在既有 Appointment 之上，多了幾個**後端算好**
 * 的欄位（02 §5.1）。前端不重算這些，只管畫色。
 */
type Cell = Appointment & {
  appointment_id: number;
  case_number: string | null;
  gender: string | null;
  billing_cycle: string | null;
  issued_receipt_no: string | null;
  is_settled: boolean;
  admin_tasks_pending: number;
  quota_label: string | null;
  is_last_quota: boolean;
};
type Summary = {
  total: number; arrived: number; no_show: number;
  pending: number; collected: number; due: number;
};
import { toLocalDateString } from "@/features/rooms/types";
import { useQueryParams, parseLocalDate } from "@/features/shared/useQueryParams";
import {
  Button,
  RoomCell,
  StatBar,
  Tabs,
  TimeGrid,
  TableSkeleton,
  ErrorState,
  cellPhase,
  minutesOfDay,
  type TimeGridColumn,
} from "@/components/ui";

/**
 * 診間日曆（櫃檯主控台）— V2升級計畫 09 §0.1 標記的「照樣本」page，
 * 後端報到三步驟（已到/未到 → 收款 → 開立收據）與房間衝突 DB 層防護
 * 已在 08 §5.3–§5.5 全部完成並測試覆蓋。
 *
 * P2（11 §6）改寫的是**格子本身**，後端流程與 CheckInPanel 的邏輯原封不動：
 *   ① 每格從「一個徽章字元 ＋ 截斷成 5 個字的姓名」變成 v7 的四行結構，
 *      並就地長出操作鍵——不必為了按「已到」而先開彈窗（v7 定案）。
 *   ② 跨格改用 rowSpan。原本是把同一筆預約在它涵蓋的每一格各畫一次，
 *      所以 90 分鐘的伴侶案看起來像三筆不同的預約。
 *   ③ 補上頂部即時統計列與「視訊／外展」欄——這兩個不佔診間，v7 定案 ⑧
 *      要求放在最右側獨立欄位依時間軸排列。
 *   ④ 空白格可點直接新增預約（v7 定案 ⑨）。
 *
 * P3（11 §4.2）把報到面板與兩個場地分頁搬到 features/rooms，這個路由檔只剩
 * 「抓當日資料 → 排進時間軸 → 決定按下去要做什麼」。
 */

export default function RoomsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [selectedDate, setSelectedDate] = useState<Date>(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  });
  // 從媒合列表「到診間日曆報到」點過來時會帶 ?date=（11 §5.9）。
  // 掛載後才讀，避免伺服器與瀏覽器算出不同初值。
  const query = useQueryParams();
  useEffect(() => {
    const d = parseLocalDate(query?.get("date"));
    if (d) setSelectedDate(d);
  }, [query]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [appts, setAppts] = useState<Cell[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Cell | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  // 三個分頁對應三種空間佔用（v7 診間日曆定案）：診間、外借的診間、5F 雲燈教室
  const [tab, setTab] = useState<"rooms" | "rentals" | "hall">("rooms");

  useEffect(() => {
    if (!token) return;
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  /**
   * 走聚合端點，不用通用的 /appointments（02 §5.1「禁止前端逐格再查」）。
   *
   * 每格的 is_settled（整格轉灰）、admin_tasks_pending、quota_label、
   * is_last_quota 都由後端一次算好。轉灰要同時看四張表且有三條規則，前端自己
   * 推會判錯——第一版就是這樣把「自費月結按完已到即轉灰」和「機構案要行政
   * 提醒全勾」兩種情形都做錯的。
   */
  const fetchAppts = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await clientFetch(
        `/room-calendar?q=${toLocalDateString(selectedDate)}`,
        token,
      );
      setAppts(data.cells);
      setSummary(data.summary);
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token, selectedDate]);

  useEffect(() => {
    fetchAppts();
  }, [fetchAppts, refreshTick]);

  // 選取的預約若剛被更新（例如報到後），從最新的 appts 清單同步內容
  useEffect(() => {
    if (!selected) return;
    const fresh = appts.find((a) => a.appointment_id === selected.appointment_id);
    if (fresh) setSelected(fresh);
  }, [appts]); // eslint-disable-line react-hooks/exhaustive-deps

  /** 直接執行、不需要填任何欄位的動作只有「已到」（v7 定案：按已到就轉已執行）。
   *  未到要填原因、收款要選付款方式、開據要選收費名目，那三步仍走 CheckInPanel，
   *  避免把同一份 API 邏輯抄成兩份。
   *
   *  **初診是第四種要填欄位的**（11 §5.9）：要一併登記身分證才產得出病歷號，
   *  所以同樣開面板。後端也擋著——直接打 check-in 會回 400，這裡只是別讓
   *  櫃檯先看到一則錯誤訊息才知道。 */
  const [busyId, setBusyId] = useState<number | null>(null);
  const quickCheckIn = useCallback(
    async (a: Cell) => {
      if (!token) return;
      if (a.first_visit) {
        setSelected(a);
        return;
      }
      setBusyId(a.appointment_id);
      try {
        await clientFetch(`/appointments/${a.appointment_id}/check-in`, token, {
          method: "PUT",
          body: JSON.stringify({ status: "arrived" }),
        });
        setRefreshTick((t) => t + 1);
      } catch (e) {
        setActionError((e as Error).message);
      } finally {
        setBusyId(null);
      }
    },
    [token],
  );
  const [actionError, setActionError] = useState<string | null>(null);

  // 聚合端點已排除 cancelled，也已附上統計列——兩者都不在前端重算。
  const live = appts;
  const stats = summary ?? { total: 0, arrived: 0, no_show: 0, pending: 0, collected: 0, due: 0 };

  /**
   * 視訊／外展不佔診間，放在最右側獨立欄位（v7 定案 ⑧，可容納每日 10 筆以上）。
   *
   * 一個欄位塞不下同時段的多筆，硬塞會讓後面那筆**靜靜消失**。所以用貪婪法
   * 把互相重疊的分到不同的 lane，通常只會有 1–2 條。
   */
  const remoteLanes = useMemo(() => {
    const remote = live
      .filter((a) => !a.room_id && a.start_time && a.end_time)
      .sort((x, y) => x.start_time!.localeCompare(y.start_time!));
    const lanes: { end: number; items: Cell[] }[] = [];
    for (const a of remote) {
      const s = minutesOfDay(a.start_time!);
      const e = minutesOfDay(a.end_time!);
      const lane = lanes.find((l) => l.end <= s);
      if (lane) {
        lane.items.push(a);
        lane.end = e;
      } else {
        lanes.push({ end: e, items: [a] });
      }
    }
    return lanes.map((l) => l.items);
  }, [live]);

  const columns: TimeGridColumn[] = useMemo(
    () => [
      ...rooms.map((r) => ({
        id: r.id,
        label: r.name,
        sub: `${r.floor}F · ${r.use_type === "兒童遊戲室" ? "👶 遊戲室" : "晤談"}`,
      })),
      ...remoteLanes.map((_, i) => ({
        id: `remote-${i}`,
        label: i === 0 ? "線上 / 外展" : `線上 / 外展 ${i + 1}`,
        sub: "不佔診間",
      })),
    ],
    [rooms, remoteLanes],
  );

  const gridItems = useMemo(() => {
    const inRoom = live
      .filter((a) => a.room_id && a.start_time && a.end_time)
      .map((a) => ({
        id: a.appointment_id,
        columnId: a.room_id!,
        startMin: minutesOfDay(a.start_time!),
        endMin: minutesOfDay(a.end_time!),
        appt: a,
      }));
    const remote = remoteLanes.flatMap((items, lane) =>
      items.map((a) => ({
        id: a.appointment_id,
        columnId: `remote-${lane}`,
        startMin: minutesOfDay(a.start_time!),
        endMin: minutesOfDay(a.end_time!),
        appt: a,
      })),
    );
    return [...inRoom, ...remote];
  }, [live, remoteLanes]);

  const prevDay = () => setSelectedDate((d) => { const n = new Date(d); n.setDate(n.getDate() - 1); return n; });
  const nextDay = () => setSelectedDate((d) => { const n = new Date(d); n.setDate(n.getDate() + 1); return n; });
  const goToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); setSelectedDate(d); };
  const dateLabel = selectedDate.toLocaleDateString("zh-TW", { year: "numeric", month: "long", day: "numeric", weekday: "short" });

  if (!token) return <p>Loading...</p>;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold text-ink">診間日曆</h1>
        <span className="text-xs text-ink-3">報到 → 收款 → 開收據，一頁完成</span>
      </div>

      <StatBar
        stats={[
          { label: "今日應到", value: stats.total },
          { label: "已報到", value: stats.arrived, tone: "done" },
          { label: "未到", value: stats.no_show, tone: stats.no_show > 0 ? "danger" : "default" },
          { label: "待報到", value: stats.pending, tone: stats.pending > 0 ? "warn" : "default" },
          { label: "今日已收", value: stats.collected, money: true, tone: "done" },
          {
            label: "尚待收款",
            value: stats.due,
            money: true,
            tone: stats.due > 0 ? "danger" : "default",
            href: "/ar",
          },
        ]}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={prevDay}>← 前一天</Button>
        <Button size="sm" variant="accent" onClick={goToday}>今天</Button>
        <Button size="sm" onClick={nextDay}>後一天 →</Button>
        <span className="text-xs font-medium text-ink-2">{dateLabel}</span>
        <input
          type="date"
          value={toLocalDateString(selectedDate)}
          onChange={(e) => {
            if (!e.target.value) return;
            const [y, m, d] = e.target.value.split("-").map(Number);
            const nd = new Date(y, m - 1, d);
            nd.setHours(0, 0, 0, 0);
            setSelectedDate(nd);
          }}
          className="rounded-control border border-line-2 bg-surface px-2 py-1 text-xs tabular-nums text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
        />
        {loading && <span className="text-[10px] text-ink-3">載入中…</span>}
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { key: "rooms", label: "診間", count: gridItems.length },
          { key: "rentals", label: "場地租借" },
          { key: "hall", label: "5F 雲燈教室" },
        ]}
      />

      {actionError && <ErrorState error={new Error(actionError)} onRetry={() => setActionError(null)} />}

      {tab === "rentals" && <RentalsTab token={token} date={selectedDate} />}
      {tab === "hall" && <HallTab token={token} date={selectedDate} />}

      {tab === "rooms" &&
        (rooms.length === 0 ? (
          <TableSkeleton rows={8} cols={6} />
        ) : (
          <TimeGrid
            columns={columns}
            items={gridItems}
            // 空白格可點直接新增預約（v7 定案 ⑨）。第二次以後由心理師自行預約，
            // 報到仍由行政在此登錄。
            onEmptyClick={(columnId, startMin) => {
              if (String(columnId).startsWith("remote")) return;
              const hh = String(Math.floor(startMin / 60)).padStart(2, "0");
              const mm = String(startMin % 60).padStart(2, "0");
              window.location.href =
                `/booking?date=${toLocalDateString(selectedDate)}&time=${hh}:${mm}&room=${columnId}`;
            }}
            renderItem={(it) => (
              <RoomCell
                appt={it.appt as any}
                onOpen={() => setSelected(it.appt)}
                onCheckIn={busyId === it.appt.appointment_id ? undefined : () => quickCheckIn(it.appt)}
                onNoShow={() => setSelected(it.appt)}
                onCollect={() => setSelected(it.appt)}
                onReceipt={() => setSelected(it.appt)}
              />
            )}
          />
        ))}

      {selected && (
        <CheckInPanel
          key={selected.id}
          appt={selected}
          token={token}
          onClose={() => setSelected(null)}
          onChanged={() => setRefreshTick((t) => t + 1)}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   報到三步驟：已到/未到 → 收款 → 開立收據
   一次只出現一步（見 V2升級計畫 03 §操作體驗細節）
   ═══════════════════════════════════════════════ */

