#!/usr/bin/env node
/**
 * 中性色階 → 語意 token 的一次性轉換 — V2升級計畫 11 §2.2。
 *
 * 全站實測有 2,178 處寫死的 Tailwind 色階，其中 **1,585 處（73%）是中性色**
 * （gray/slate/zinc/…）。這些是可以機械轉換的：它們表達的只是「主要文字 /
 * 次要文字 / 框線 / 底色」這幾個層級，沒有語境依賴。
 *
 * 剩下的 593 處語意色（紅綠琥珀…）**不在這支的範圍內**——那些要看「這個紅色
 * 在講什麼」才能決定對應到哪個 --st-*，機械轉換只會把錯誤變得整齊。
 *
 *   node scripts/codemod-neutrals.mjs --dry    只看會改什麼
 *   node scripts/codemod-neutrals.mjs          實際改
 */

import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const DRY = process.argv.includes("--dry");

/**
 * 對應表。分三層文字、兩層框線、兩層底色——跟 globals.css 的 token 一致。
 *
 * 刻意把 500/400/300 都收進 ink-3：原本那三階在不同頁面被當成同一種「次要
 * 說明文字」用，保留三階只會讓不一致延續下去。真正需要更淡的地方用 st-muted。
 */
const MAP = new Map(
  Object.entries({
    // ── 文字 ──────────────────────────────────────────────
    "text-{N}-950": "text-ink",
    "text-{N}-900": "text-ink",
    "text-{N}-800": "text-ink",
    "text-{N}-700": "text-ink-2",
    "text-{N}-600": "text-ink-2",
    "text-{N}-500": "text-ink-3",
    "text-{N}-400": "text-ink-3",
    "text-{N}-300": "text-st-muted",
    "text-{N}-200": "text-st-muted",
    // ── 框線 ──────────────────────────────────────────────
    "border-{N}-400": "border-line-2",
    "border-{N}-300": "border-line-2",
    "border-{N}-200": "border-line",
    "border-{N}-100": "border-line",
    "border-{N}-50": "border-line",
    "divide-{N}-200": "divide-line",
    "divide-{N}-100": "divide-line",
    // ── 底色 ──────────────────────────────────────────────
    // 刻意不收 bg-{N}-600..900：那幾個都是深色實心按鈕，而且都帶著更深的
    // hover（bg-gray-800 hover:bg-gray-900）。中性色只有 ink 一階那麼深，
    // 機械轉換會把兩階壓成同一階、hover 靜靜消失。那 8 處手工處理。
    "bg-{N}-300": "bg-line-2",
    "bg-{N}-200": "bg-surface-3",
    "bg-{N}-100": "bg-surface-3",
    "bg-{N}-50": "bg-surface-2",
    // ── 其他 ──────────────────────────────────────────────
    "ring-{N}-300": "ring-line-2",
    "ring-{N}-200": "ring-line",
    "placeholder-{N}-400": "placeholder-ink-3",
    "placeholder-{N}-300": "placeholder-st-muted",
  }),
);

const NEUTRALS = ["gray", "slate", "zinc", "neutral", "stone"];

/** 展開成具體的類別名稱對照。 */
const TABLE = new Map();
for (const [tpl, to] of MAP) {
  for (const n of NEUTRALS) TABLE.set(tpl.replace("{N}", n), to);
}

/** 註解換成等長空白，避免動到說明文字裡引用的舊寫法。 */
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

const files = walk(join(ROOT, "src"));
let totalHits = 0;
const perFile = [];

for (const file of files) {
  const src = readFileSync(file, "utf8");
  const masked = maskComments(src);
  let hits = 0;
  let out = "";
  let last = 0;

  // 在「未被遮蔽」的位置上做替換，逐一比對 TABLE 的 key
  const re = new RegExp(
    `\\b(?:${[...TABLE.keys()].map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`,
    "g",
  );
  for (const m of masked.matchAll(re)) {
    out += src.slice(last, m.index) + TABLE.get(m[0]);
    last = m.index + m[0].length;
    hits++;
  }
  out += src.slice(last);

  if (hits) {
    totalHits += hits;
    perFile.push([relative(ROOT, file), hits]);
    if (!DRY) writeFileSync(file, out);
  }
}

perFile.sort((a, b) => b[1] - a[1]);
console.log(`${DRY ? "[dry-run] " : ""}轉換 ${totalHits} 處，${perFile.length} 個檔案\n`);
for (const [f, n] of perFile.slice(0, 15)) console.log(`  ${String(n).padStart(4)}  ${f}`);
if (perFile.length > 15) console.log(`  … 另外 ${perFile.length - 15} 個檔案`);
