import { PhasePlaceholder } from "@/components/phase-placeholder";

export default function StatsPage() {
  return (
    <PhasePlaceholder
      title="我的數據"
      phase={7}
      summary="只呈現自己的數據，不與其他心理師橫向比較。"
      contents={[
        "到案率、留案率、黏著度分布、媒合成功率",
        "可切換週／月／季與自訂區間，數字可下鑽到個案清單",
        "時段分析的空檔可一鍵登記為可當診時段",
      ]}
      blocked="Q18 目標值由誰設定／Q19 空間使用率分母／留案率算法"
    />
  );
}
