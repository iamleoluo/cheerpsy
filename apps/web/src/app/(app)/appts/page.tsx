import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function ApptsPage() {
  return (
    <PhasePlaceholder
      title="預約總表"
      phase={3}
      summary="跨日期區間的查詢與稽核總表，第一欄綁病歷號。"
      contents={[
        "可篩選、可匯出 CSV",
        "行政確認欄可按已到／未到（與診間日曆同一份資料）",
        "視訊／外展列顯示「心理師端確認」",
      ]}
      movedFrom="/cases 的 AppointmentsTab"
    />
  );
}
