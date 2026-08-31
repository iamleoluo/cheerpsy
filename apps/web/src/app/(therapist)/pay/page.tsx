import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function PayPage() {
  return (
    <PhasePlaceholder
      title="我的酬勞"
      phase={6}
      summary="資料來源為月報表；結算區間當月 1 日～月末，隔月 25 日發放。"
      contents={[
        "酬勞明細（可依月份查詢、可匯出）",
        "抽成率在場次結算當下鎖定；鐘點費回溯修改不自動重算，改人工調整",
        "只看得到自己的酬勞，看不到個案付款狀態與收據",
      ]}
      movedFrom="/finance 的 payouts 分頁"
      blocked="Q12 失約費是否計酬／Q13 是否顯示扣繳"
    />
  );
}
