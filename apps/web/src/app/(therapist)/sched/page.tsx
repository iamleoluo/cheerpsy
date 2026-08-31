import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function SchedPage() {
  return (
    <PhasePlaceholder
      title="我的班表"
      phase={3}
      summary="個人週行事曆，橫軸星期、縱軸時間；不是空間表。"
      contents={[
        "08:00–22:00、30 分半格，90 分鐘伴侶案自動跨格",
        "頂部固定顯示下一場預約與倒數",
        "線上／外展可直接在方塊上操作（預設已到，個案沒來才按取消）",
        "機構最後一次加紅框提示",
      ]}
    />
  );
}
