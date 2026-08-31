import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function ArPage() {
  return (
    <PhasePlaceholder
      title="應收帳冊"
      phase={4}
      summary="三個分頁分的是追款方式，不是付款狀態。"
      contents={[
        "未收：該當場收卻沒收到的，逾期天數自動分色",
        "月結：本來就約定月底結的，可整批產生帳單（承接原 /claims 的 SelfPayTab）",
        "機構應收：等機構撥款，與核銷案連動",
      ]}
      movedFrom="/finance 的 tracking 分頁"
    />
  );
}
