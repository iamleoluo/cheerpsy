import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * 合併 className，後者覆蓋前者的同類 utility。
 *
 * 之所以需要 twMerge 而不是單純 clsx：元件會有預設樣式、呼叫端會想覆蓋其中
 * 一項。`cn("px-3 py-2", "px-4")` 要得到 `py-2 px-4`，而不是兩個 px 都留著
 * 讓 CSS 順序決定勝負。
 *
 * clsx / tailwind-merge 在 package.json 裡本來就有（連同 cva 與 lucide-react），
 * 但在 P0 之前全專案 0 個檔案用到。
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
