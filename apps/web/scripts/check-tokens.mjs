#!/usr/bin/env node
/**
 * Token 守門員 — V2升級計畫 11 §2.2
 *
 * 規則只有一條：**元件不准直接寫 Tailwind 色階**（text-red-600、bg-emerald-100
 * …），一律走語意 token（text-st-danger、bg-st-done-bg）。
 *
 * 為什麼需要這支：11 §1.1 掃出同一個「未收 / 未到 / 逾期」語意散成 5 個紅色階
 * （red-600 38 次、red-500 32 次、rose-600 31 次、rose-500 18 次、red-700 18 次），
 * 綠 4 種、琥珀 5 種。這不是誰不小心，是沒有東西擋著。
 *
 * 為什麼不是 ESLint：專案目前沒裝 ESLint，而導入後既有 19,558 行會噴出大量
 * 與本規則無關的既有問題，真正該擋的那條會被淹掉。這支零相依、只做一件事。
 *
 * 範圍刻意只涵蓋「新寫的」目錄。既有 33 頁不在守備範圍內——P0 的紀律是純新增、
 * 不回頭改舊頁；那些頁面會在 P2–P5 各自被重寫時自然進入範圍。
 *
 *   node scripts/check-tokens.mjs          檢查
 *   node scripts/check-tokens.mjs --stats  另外報告既有頁面的色階使用量
 */

import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;

/** 新程式碼：必須走 token。 */
const GUARDED = ["src/components/ui", "src/features"];
/** 既有程式碼：只統計，不擋。 */
const LEGACY = ["src/app", "src/components"];

const PALETTES = [
  "slate", "gray", "zinc", "neutral", "stone",
  "red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal",
  "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia", "pink", "rose",
].join("|");
const UTILS = "text|bg|border|ring|divide|from|via|to|decoration|outline|shadow|accent|fill|stroke|placeholder";

const BANNED = new RegExp(`\\b(?:${UTILS})-(?:${PALETTES})-\\d{2,3}\\b`, "g");

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|jsx?)$/.test(p)) out.push(p);
  }
  return out;
}

function scan(dirs) {
  const hits = [];
  for (const d of dirs) {
    for (const file of walk(join(ROOT, d))) {
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        for (const m of line.matchAll(BANNED)) {
          hits.push({ file: relative(ROOT, file), line: i + 1, cls: m[0] });
        }
      });
    }
  }
  return hits;
}

const violations = scan(GUARDED);

if (process.argv.includes("--stats")) {
  const counts = new Map();
  for (const h of scan(LEGACY)) counts.set(h.cls, (counts.get(h.cls) ?? 0) + 1);
  const sorted = [...counts].sort((a, b) => b[1] - a[1]);
  const total = sorted.reduce((s, [, n]) => s + n, 0);
  console.log(`\n既有頁面的原始色階使用量：${total} 處，${sorted.length} 種`);
  console.log("（不擋，供追蹤 P2–P5 重寫進度用。前 12 名：）");
  for (const [cls, n] of sorted.slice(0, 12)) {
    console.log(`  ${String(n).padStart(4)}  ${cls}`);
  }
  console.log("");
}

if (violations.length === 0) {
  console.log(`✓ token 檢查通過（守備範圍：${GUARDED.join(", ")}）`);
  process.exit(0);
}

console.error(`\n✗ 發現 ${violations.length} 處直接使用 Tailwind 色階：\n`);
for (const v of violations) {
  console.error(`  ${v.file}:${v.line}  ${v.cls}`);
}
console.error(`
改用語意 token（V2升級計畫 11 §2.2）：
  未收 / 未到 / 退回 / 作廢     → text-st-danger   bg-st-danger-bg
  已收 / 已核銷 / 已入帳        → text-st-done     bg-st-done-bg
  額度將盡 / 逾期 / 缺件        → text-st-warn     bg-st-warn-bg
  已到未收 / 收集中 / 媒合中    → text-st-active   bg-st-active-bg
  待報到 / 待送出 / 待回覆      → text-st-pending  bg-st-pending-bg
  已結案 / 整格轉灰             → text-st-muted    bg-st-muted-bg
  一般文字 / 框線 / 底色        → text-ink|ink-2|ink-3  border-line  bg-surface
`);
process.exit(1);
