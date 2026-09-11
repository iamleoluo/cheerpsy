#!/usr/bin/env node
/**
 * `primary-*` 色階 → `accent` token — V2升級計畫 11 §2.2 第二輪。
 *
 * primary 是 tailwind.config.ts 裡手寫的品牌藍色階（P0 刻意原封不動保留，
 * 好讓既有 33 頁在重寫之前不變樣）。全站 301 處。
 *
 * 它跟語意色不一樣，**不需要逐處判斷**：primary 從頭到尾只表達同一件事
 * ——「這是可以按的主要動作 / 這是被選取的那一個」。所以整批對到 accent。
 *
 * 唯一需要看前綴的是 600/700 這一對：實測 `bg-primary-700` 60 處**全部**
 * 帶著 hover:，也就是那個標準的「主按鈕 ＋ 更深的 hover」。對過去正好是
 * Button 的 accent variant 已經在用的 `bg-accent hover:bg-st-active`。
 *
 *   node scripts/codemod-primary.mjs --dry
 */

import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const DRY = process.argv.includes("--dry");

const TABLE = new Map(
  Object.entries({
    // ── 實心 ──────────────────────────────────────────────
    "bg-primary-700": "bg-st-active", // 全數是 hover:，比 accent 深一階
    "bg-primary-600": "bg-accent",
    "bg-primary-500": "bg-accent",
    "bg-primary-400": "bg-accent/70", // 長條圖與進度條，原本就刻意淡一階
    "bg-primary-200": "bg-accent/20", // chip 的 hover
    "bg-primary-100": "bg-accent-soft",
    "bg-primary-50": "bg-accent-soft",
    // ── 文字 ──────────────────────────────────────────────
    "text-primary-800": "text-accent",
    "text-primary-700": "text-accent",
    "text-primary-600": "text-accent",
    "text-primary-500": "text-accent",
    // ── 框線 ──────────────────────────────────────────────
    "border-primary-600": "border-accent",
    "border-primary-500": "border-accent",
    "border-primary-300": "border-accent/40",
    "border-primary-200": "border-accent/40",
    "ring-primary-500": "ring-accent",
    // ── 表單控制項的 accent-color ─────────────────────────
    // Tailwind 的 accent-* 與我們的顏色 token 同名，寫 accent-accent 會很怪，
    // 直接用任意值指到同一個變數
    "accent-primary-600": "accent-[hsl(var(--accent))]",
  }),
);

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

const re = new RegExp(`\\b(?:${[...TABLE.keys()].join("|")})\\b`, "g");
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
