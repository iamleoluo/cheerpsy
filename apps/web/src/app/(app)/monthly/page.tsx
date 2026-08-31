import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function MonthlyPage() {
  return (
    <PhasePlaceholder
      title="月報表"
      phase={4}
      summary="資料來源只有一個：日報表按下「完成當日對帳」後寫入的每日紀錄。"
      contents={[
        "每日對帳彙總（可展開當日明細）；未對帳的日標「待對帳」，金額不計入合計",
        "心理師當月收入五欄：諮商收入｜講師費｜督導收入｜場地費扣項｜合計",
        "主管覆核紀錄：對帳鎖定後解鎖修改的紀錄",
        "補收款自動回寫該日，標小字「MM/DD 補收 $X」，不列入覆核",
        "結算區間當月 1 日～月末，薪資發放日隔月 25 日",
      ]}
    />
  );
}
