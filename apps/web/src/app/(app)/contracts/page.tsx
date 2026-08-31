import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function ContractsPage() {
  return (
    <PhasePlaceholder
      title="機構合約清冊"
      phase={1}
      summary="機構 → 合約 → 方案三層的中間層，定義錢的規則。"
      contents={[
        "方案鐘點費／個案自付額／身份條件／總核銷上限（金額或次數或不限）",
        "承辦人與聯絡電話、合約有效期",
        "核銷區間匯入",
      ]}
    />
  );
}
