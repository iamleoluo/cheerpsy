import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function PlansPage() {
  return (
    <PhasePlaceholder
      title="機構方案清冊"
      phase={1}
      summary="由合約開出的年度方案，以及掛在方案下的個案額度。"
      contents={[
        "方案清冊：每人次數／年度總次數／有效起訖／狀態",
        "子列表（個案清冊）：額度三態長條 已使用 + 已預約 + 已預留 = 個人上限",
        "方案層交通費模式（可多個選項供心理師挑選）",
      ]}
      movedFrom="/cases 的 QuotasTab 與 TemplatesSection"
      blocked="Q9 預留有效期／Q10 跨年度額度／Q11 年度總量預警"
    />
  );
}
