import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function PoolPage() {
  return (
    <PhasePlaceholder
      title="派案邀請"
      phase={2}
      summary="行政派案後推播到此，先回先得。"
      contents={[
        "三分頁：待回覆／已承接／已結束",
        "卡片顯示主述議題、議題補充說明、諮商型態、是否指定、另有幾位心理師評估中",
        "願意承接 → 填 1–3 個可預約時段（第一個必填）",
        "無意願承接 → 婉拒原因四選一",
      ]}
    />
  );
}
