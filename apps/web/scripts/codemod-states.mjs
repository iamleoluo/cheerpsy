#!/usr/bin/env node
/**
 * 語意色階 → 六個狀態 token（危險／注意／完成）— V2升級計畫 11 §2.2 第三輪。
 *
 * 這一支**只處理淺色底與文字**，也就是「這件事現在怎麼了」在畫面上的兩種
 * 表現：徽章（淺底＋深字）與提示框。這三個色系在本專案的用法從頭到尾一致，
 * badge.tsx 的六個 tone 本來就是照著這份清單挑出來的：
 *
 *     紅 / 玫瑰   → danger  未收、未到、逾期、作廢、錯誤
 *     琥珀 / 黃 / 橘 → warn  額度將盡、缺件、退回補件
 *     綠 / 翠      → done   已收、已核銷、已入帳
 *
 * **刻意不碰兩類東西**，因為它們不是「機械對應」而是「要重新決定」：
 *
 *   ① 實心彩色按鈕（bg-rose-600、bg-green-600…）
 *      v7 定案 ③ 明文禁止：「已到／未到按鈕改為中性黑白，狀態改由圖示標色」。
 *      一天要掃 38 格的畫面上，按鈕也有顏色的話眼睛就沒辦法用顏色掃狀態。
 *      把它們轉成 bg-st-danger 只是把違規做得更整齊——那 20 幾處要逐個改成
 *      neutral / solid / danger variant。
 *
 *   ② 藍色系
 *      藍在這個專案身兼三職：說明框、文字連結、狀態徽章。一律對到某個 token
 *      一定會錯，分開處理。
 *
 *   node scripts/codemod-states.mjs --dry
 */

import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const DRY = process.argv.includes("--dry");

/** 色系 → tone。 */
const TONE = {
  red: "danger",
  rose: "danger",
  amber: "warn",
  yellow: "warn",
  orange: "warn",
  green: "done",
  emerald: "done",
};

const TABLE = new Map();
for (const [hue, tone] of Object.entries(TONE)) {
  // 文字：400–800 全部收斂成同一階。原本一個語意散成 5 個色階（11 §1.1），
  // 保留階數只會讓同一件事在不同頁面看起來像不同事
  for (const s of [400, 500, 600, 700, 800]) TABLE.set(`text-${hue}-${s}`, `text-st-${tone}`);
  // 淺底：徽章與提示框
  for (const s of [50, 100, 200]) TABLE.set(`bg-${hue}-${s}`, `bg-st-${tone}-bg`);
  // 框線：淺階當柔和外框，深階當實線
  for (const s of [100, 200, 300]) TABLE.set(`border-${hue}-${s}`, `border-st-${tone}/30`);
  for (const s of [500, 600, 700]) TABLE.set(`border-${hue}-${s}`, `border-st-${tone}`);
}

function maskComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, "\0"))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p1) => p1 + "\0".repeat(m.length - p1.length));
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|jsx?)$/.test(p)) out.push(p);
  }
  return out;
}

// 長的 key 排前面，避免 bg-red-50 先吃掉 bg-red-500 的前半
const keys = [...TABLE.keys()].sort((a, b) => b.length - a.length);
const re = new RegExp(`\\b(?:${keys.join("|")})\\b`, "g");

let total = 0;
const perFile = [];
for (const file of walk(join(ROOT, "src"))) {
  const src = readFileSync(file, "utf8");
  const masked = maskComments(src);
  let out = "";
  let last = 0;
  let hits = 0;
  for (const m of masked.matchAll(re)) {
    out += src.slice(last, m.index) + TABLE.get(m[0]);
    last = m.index + m[0].length;
    hits++;
  }
  out += src.slice(last);
  if (hits) {
    total += hits;
    perFile.push([relative(ROOT, file), hits]);
    if (!DRY) writeFileSync(file, out);
  }
}

perFile.sort((a, b) => b[1] - a[1]);
console.log(`${DRY ? "[dry-run] " : ""}轉換 ${total} 處，${perFile.length} 個檔案\n`);
for (const [f, n] of perFile.slice(0, 12)) console.log(`  ${String(n).padStart(4)}  ${f}`);
if (perFile.length > 12) console.log(`  … 另外 ${perFile.length - 12} 個檔案`);
