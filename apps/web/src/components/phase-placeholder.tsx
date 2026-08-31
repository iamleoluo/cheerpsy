/**
 * Phase 0 佔位卡。
 *
 * 每個尚未實作的頁面共用這張卡，標明它排在哪個 Phase、會有什麼內容、
 * 以及內容目前是否寄居在別的頁面（Phase 3 起會逐一搬出）。
 * 對應 document_reference/gap_analysis.md §4。
 */
export function PhasePlaceholder({
  title,
  phase,
  summary,
  contents,
  movedFrom,
  blocked,
}: {
  title: string;
  phase: number;
  summary: string;
  /** 這一頁完成後會有的東西 */
  contents?: readonly string[];
  /** 內容目前住在哪個既有頁面 */
  movedFrom?: string;
  /** 尚未解決的 open question，如 "Q6" */
  blocked?: string;
}) {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-1 flex items-center gap-3">
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700">
          Phase {phase}
        </span>
      </div>
      <p className="mb-6 text-sm text-gray-500">{summary}</p>

      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6">
        <p className="text-sm font-medium text-gray-700">
          本頁於 Phase {phase} 實作
        </p>

        {contents && contents.length > 0 && (
          <ul className="mt-3 space-y-1.5 text-sm text-gray-600">
            {contents.map((c) => (
              <li key={c} className="flex gap-2">
                <span className="text-gray-400">·</span>
                <span>{c}</span>
              </li>
            ))}
          </ul>
        )}

        {movedFrom && (
          <p className="mt-4 rounded-lg bg-white px-3 py-2 text-xs text-gray-500">
            內容目前位於 <code className="text-gray-700">{movedFrom}</code>，屆時搬移至此。
          </p>
        )}

        {blocked && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            待決事項：{blocked}（見 <code>document_reference/open_questions.md</code>）
          </p>
        )}
      </div>

      <p className="mt-4 text-xs text-gray-400">
        規劃詳見 document_reference/gap_analysis.md §4
      </p>
    </div>
  );
}
