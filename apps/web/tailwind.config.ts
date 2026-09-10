import type { Config } from "tailwindcss";

/**
 * V2升級計畫 11 §2 的 token 對接層。
 *
 * P0 紀律：純新增。`primary` 與 Tailwind 全部預設色階原封不動保留，
 * 所以既有 33 頁的 className 全部照舊生效、畫面零變化；新的語意色從 P1
 * 的元件庫才開始使用。
 *
 * 顏色定義在 globals.css 的 :root（HSL 三通道），這裡只做 Tailwind 對接，
 * 並保留 <alpha-value> 讓 bg-st-danger/10 這種寫法可用。
 */

/** 把 HSL 三通道 token 包成 Tailwind 看得懂的、支援透明度修飾詞的顏色。 */
const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // ── 既有，不動 ──────────────────────────────────────────────
        primary: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          200: "#bae6fd",
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          800: "#075985",
          900: "#0c4a6e",
        },

        // ── 新增：中性 ─────────────────────────────────────────────
        paper: token("paper"),
        surface: {
          DEFAULT: token("surface"),
          2: token("surface-2"),
          3: token("surface-3"),
        },
        ink: {
          DEFAULT: token("ink"),
          2: token("ink-2"),
          3: token("ink-3"),
        },
        line: {
          DEFAULT: token("line"),
          2: token("line-2"),
        },

        // ── 新增：品牌 ─────────────────────────────────────────────
        accent: {
          DEFAULT: token("accent"),
          fg: token("accent-fg"),
          soft: token("accent-soft"),
        },

        // ── 新增：語意狀態（11 §2.2）──────────────────────────────
        // 用法：text-st-danger / bg-st-danger-bg / border-st-danger/30
        st: {
          pending: token("st-pending"),
          "pending-bg": token("st-pending-bg"),
          active: token("st-active"),
          "active-bg": token("st-active-bg"),
          done: token("st-done"),
          "done-bg": token("st-done-bg"),
          warn: token("st-warn"),
          "warn-bg": token("st-warn-bg"),
          danger: token("st-danger"),
          "danger-bg": token("st-danger-bg"),
          muted: token("st-muted"),
          "muted-bg": token("st-muted-bg"),
        },
      },

      fontFamily: {
        sans: "var(--font-sans)",
        mono: "var(--font-mono)",
      },

      // 三檔密度（11 §2.5）。compact 給診間格與流水帳，一屏要塞得下一整天；
      // data 給清單與表單；display 給 KPI 與對帳總額。
      fontSize: {
        compact: ["11.5px", { lineHeight: "1.5" }],
        data: ["13.5px", { lineHeight: "1.7" }],
        "display-sm": ["20px", { lineHeight: "1.25", letterSpacing: "-0.02em", fontWeight: "700" }],
        "display-md": ["28px", { lineHeight: "1.15", letterSpacing: "-0.03em", fontWeight: "800" }],
        "display-lg": ["34px", { lineHeight: "1.1", letterSpacing: "-0.03em", fontWeight: "800" }],
      },

      // 刻意「不」覆寫 Tailwind 預設的 rounded-sm/DEFAULT/lg——既有頁面用了
      // 30 次 rounded-lg，覆寫等於偷偷改掉所有現存畫面。改用獨立命名，
      // 由 P1 的元件庫使用。
      borderRadius: {
        badge: "var(--radius-sm)",
        control: "var(--radius)",
        card: "var(--radius-lg)",
      },

      boxShadow: {
        1: "var(--shadow-1)",
        2: "var(--shadow-2)",
        modal: "var(--shadow-modal)",
      },
    },
  },
  plugins: [],
};
export default config;
