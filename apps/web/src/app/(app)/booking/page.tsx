import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function BookingPage() {
  return (
    <PhasePlaceholder
      title="預約作業"
      phase={3}
      summary="左表單 ＋ 右診間週檢視，邊訂邊看空間。"
      contents={[
        "新增預約（單筆）",
        "批次預約（每週／每兩週／每月，含國定假日提醒）",
        "診間空間週檢視",
        "每次預約可當下選填自費／機構與當次金額（D1）",
      ]}
      movedFrom="/cases 的 AppointmentForm 與 BatchForm"
    />
  );
}
