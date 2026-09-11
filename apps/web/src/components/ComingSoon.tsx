/**
 * V2 前端重構期間的佔位頁。導覽已依 09_機構與財務前端重構規劃.html 的新 IA
 * 全部建好，避免點擊 404；頁面本體依 09 §6 的建議順序逐一補上。
 */
export function ComingSoon({
  title,
  note,
}: {
  title: string;
  note?: string;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-3 text-4xl">🚧</div>
      <h2 className="mb-1 text-lg font-semibold text-ink-2">{title}</h2>
      <p className="max-w-md text-sm text-ink-3">
        {note ?? "這頁還在施工中，依 V2升級計畫 09 的建議順序陸續建置。"}
      </p>
    </div>
  );
}
