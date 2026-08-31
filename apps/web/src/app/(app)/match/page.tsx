import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function MatchPage() {
  return (
    <PhasePlaceholder
      title="媒合管理"
      phase={2}
      summary="諮商需求表 → 派案 → 心理師承接 → 轉預約 → 初診有到 → 產生病歷號。"
      contents={[
        "媒合列表（派案碼／指定心理師／媒合狀態，點列展開派案批次子列表）",
        "媒合結案表",
        "諮商需求表（表單樣式）",
        "派案：同時發送 1–3 位、先回先得；逾 1 天提醒、逾 3 個自然日自動退回",
      ]}
    />
  );
}
