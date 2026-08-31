import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function TodayPage() {
  return (
    <PhasePlaceholder
      title="我的今日"
      phase={6}
      summary="今天要做什麼，以及別人在等我什麼。"
      contents={[
        "今日班表（現場個案由櫃檯報到，此處僅顯示狀態）",
        "待辦依急迫度排序：派案邀請 → 文件確認 → 未寫紀錄 → 額度提醒",
        "不顯示收款金額、他人個案與所內總營收",
      ]}
      blocked="Q21 諮商紀錄是否納入系統"
    />
  );
}
