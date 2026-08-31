import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function DocsPage() {
  return (
    <PhasePlaceholder
      title="文件確認"
      phase={5}
      summary="機構核銷需雙重把關：心理師確認文件 ＋ 行政核對。"
      contents={[
        "未確認／已確認文件兩分頁，可單筆或批次確認",
        "上傳附件三類：領據／月次清冊表／其他",
        "只看得到自己負責的紀錄，不顯示請款金額與收據",
      ]}
      movedFrom="/claims 的 DocConfirmTab"
      blocked="Q（各機構附件是否必傳）／代確認機制"
    />
  );
}
