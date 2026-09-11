import { Fragment } from "react";

/**
 * 只認一種標記：`**粗體**`。
 *
 * 操作說明裡常常需要在一句話中間標出關鍵詞（「**出席驅動**：按了已到才產生
 * 場次」），整句加粗會失去重點、完全不加又讀不出哪裡重要。引入一個
 * markdown 套件為了一種語法不划算，所以只實作這一種。
 *
 * 不支援巢狀、不支援其他語法——內容是我們自己寫的，不是使用者輸入，
 * 所以不需要處理惡意標記；奇數個 `**` 會原樣印出來，那是寫錯的提示。
 */
export function RichText({ children }: { children: string }) {
  const parts = children.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((part, i) =>
        // split 帶捕獲群組時，奇數索引就是被包起來的內容
        i % 2 === 1 ? (
          <b key={i} className="font-bold text-ink">{part}</b>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
