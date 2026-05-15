"use client";

import { useState } from "react";

/* ───── types ───── */
interface DocSection {
  type: "steps" | "tips" | "notes" | "text" | "flow";
  heading: string;
  items: string[];
}

interface DocModule {
  id: string;
  icon: string;
  title: string;
  href: string;
  tagline: string;
  overview: string;
  sections: DocSection[];
}

/* ───── content ───── */
const modules: DocModule[] = [
  {
    id: "overview",
    icon: "🗺️",
    title: "系統總覽",
    href: "/dashboard",
    tagline: "了解 CheerPsy 的核心流程與角色",
    overview:
      "CheerPsy 以「預約驅動」為核心設計：行政建立預約 → 隔日系統自動結算 → 諮商紀錄自動寫入流水帳 → 行政完成收款或請款 → 月底報表自動彙整。多數流程無需手動輸入。",
    sections: [
      {
        type: "flow",
        heading: "核心工作流程",
        items: [
          "建立個案 → 個案管理",
          "建立預約 → 預約日曆",
          "T+1 日結（系統自動）",
          "收款 / 請款 → 日結帳冊 + 核銷案管理",
          "心理師酬勞月結 → 財務管理",
          "查看月度損益 → 營運報表",
        ],
      },
      {
        type: "text",
        heading: "角色與權限概覽",
        items: [
          "管理員：所有功能 + 解鎖帳務 + 修改歷史紀錄 + 帳號管理",
          "行政人員：個案管理、預約排程、收款請款、酬勞月結、零用金、報表查看",
          "心理師：查看個人預約與流水帳、建立/取消預約、確認諮商文件",
        ],
      },
      {
        type: "tips",
        heading: "重要規則",
        items: [
          "T+1 原則：當日個案未到請當日取消預約，逾時系統視為已執行無法撤回",
          "70/30 拆帳：系統依各心理師抽成比例自動計算，無需手動輸入",
          "帳務鎖定：已發生日期的帳務由系統鎖定，管理員解鎖需填原因並留存稽核紀錄",
          "機構墊付：機構個案完成後先付心理師，機構到款前診所墊付，月報表追蹤墊付金額",
        ],
      },
    ],
  },
  {
    id: "cases",
    icon: "👤",
    title: "個案管理",
    href: "/cases",
    tagline: "Stage 1 快速建檔，初診後補填轉正式",
    overview:
      "個案管理採用兩階段設計：預約時只需填基本資料（Stage 1），初診到場後補填完整資料並「轉正式」產生永久案號（Stage 2）。",
    sections: [
      {
        type: "steps",
        heading: "Stage 1：新增預約個案",
        items: [
          "點「＋新增個案」",
          "填入姓名、電話、年齡（估算用，初診前不需精確）",
          "指定負責心理師",
          "選付費方式（自費 / 機構），機構需選對應機構名稱",
          "選結帳週期（單次 / 月結 / 多次）",
          "儲存後個案狀態為「已預約未初談」，系統自動分配流水序號 #000X",
        ],
      },
      {
        type: "steps",
        heading: "Stage 2：初診後轉為正式個案",
        items: [
          "個案初診到場後，點個案列表的「編輯」",
          "補填「轉正式所需資料」區塊：性別、出生日期、身份證字號（必填）",
          "補填緊急聯絡人、聯絡電話",
          "可選填地址、市話、轉介來源、會談地點、初談日期",
          "儲存後點「轉正式」按鈕",
          "系統自動產生正式案號（格式：西元年後2碼 + 流水號 + 身份證末2碼，例：26000145）",
          "狀態自動變為「進行中」",
        ],
      },
      {
        type: "text",
        heading: "狀態流程",
        items: [
          "已預約未初談 → 轉正式後變為「進行中」",
          "進行中 → 可手動改為「暫停」或「結案」或「流失」",
          "編輯個案時狀態下拉不顯示「已預約未初談」（只能透過新增產生）",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "身份證字號使用 AES 加密儲存，管理員也無法直接查看原始值",
          "轉正式後案號不可修改，確認再按",
          "可用「匯出 CSV」匯出所有個案清單",
        ],
      },
      {
        type: "tips",
        heading: "注意事項",
        items: [
          "機構個案請務必選對機構，影響核銷案編號與請款流程",
          "結帳週期「月結」代表月底統一出帳，請確認與個案的實際付費方式一致",
        ],
      },
    ],
  },
  {
    id: "calendar",
    icon: "📅",
    title: "預約日曆",
    href: "/calendar",
    tagline: "排程中心，預約驅動帳務自動化",
    overview:
      "所有諮商都從預約開始。新增預約後，系統在 T+1（隔日）自動執行日結，將昨日已執行的預約寫入流水帳，無需手動操作。",
    sections: [
      {
        type: "steps",
        heading: "新增單次預約",
        items: [
          "點「＋新增預約」（或在月曆空格點擊）",
          "選個案（可輸入姓名搜尋）",
          "選心理師、諮商類型（現場 / 線上 / 家訪）、診間",
          "選日期、起始時間（預設 50 分鐘）",
          "填入諮商費用（系統依抽成比例自動計算各方份額）",
          "儲存",
        ],
      },
      {
        type: "steps",
        heading: "批次預約（定期諮商）",
        items: [
          "點「批次預約」",
          "選個案、心理師、類型、診間",
          "設定起始日期、頻率（每週 / 隔週）、總次數",
          "系統自動產生排程，顯示預覽清單",
          "確認後一次建立所有預約",
        ],
      },
      {
        type: "steps",
        heading: "取消預約",
        items: [
          "在月曆或預約列表找到該筆預約",
          "點「取消」並確認",
          "當日取消不計費，隔日日結後視為已執行",
        ],
      },
      {
        type: "tips",
        heading: "T+1 日結規則",
        items: [
          "每日 00:00 後前一日的預約自動結算：未取消 → 已執行；已取消 → 不計費",
          "個案未到請務必在當日結束前取消，否則帳務自動產生",
          "管理員執行「日結」可補跑指定日期區間的結算",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "預約建立後若需修改費用，可在流水帳解鎖後調整",
          "診間衝突由系統自動阻擋（PostgreSQL EXCLUDE GIST），不同心理師同診間同時段無法預約",
        ],
      },
    ],
  },
  {
    id: "ledger",
    icon: "📒",
    title: "日結帳冊",
    href: "/ledger",
    tagline: "自動寫入的諮商財務台帳",
    overview:
      "日結帳冊由系統在 T+1 自動寫入，無需手動輸入諮商記錄。行政需要做的是：確認收款狀態、填入收款資訊、最後鎖定。",
    sections: [
      {
        type: "steps",
        heading: "執行日結",
        items: [
          "每日進入日結帳冊，點「執行日結」",
          "系統自動將前一日未取消的預約寫入帳冊",
          "確認新增筆數無誤",
          "若需補跑歷史日期，點「執行日結」後可選日期區間",
        ],
      },
      {
        type: "steps",
        heading: "自費收款",
        items: [
          "找到待收款的自費紀錄",
          "點「收款」按鈕",
          "選付款方式：現金 / 匯款",
          "匯款需填入帳戶末 5 碼作為憑據",
          "確認後狀態變為「已收款」",
        ],
      },
      {
        type: "steps",
        heading: "機構請款",
        items: [
          "找到待請款的機構紀錄",
          "點「請款」，填入請款單號（請款單據上的編號）",
          "狀態變為「請款中」",
          "款項到帳後點「到款」，填入到款收據或匯款單號",
          "狀態更新為「已核銷」",
        ],
      },
      {
        type: "steps",
        heading: "鎖定帳務",
        items: [
          "確認該筆帳務資訊正確無誤",
          "點「鎖定」，該筆紀錄進入唯讀狀態",
          "如需修正：點「解鎖」→ 填寫修改原因 → 修改後重新鎖定",
          "所有解鎖操作均記錄於稽核日誌",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "篩選條件：可依心理師、月份、付費方式、收款狀態快速過濾",
          "匯出 CSV 可匯出當前篩選結果，用於外部對帳",
          "諮商日期、金額等核心欄位一旦建立無法直接修改，需解鎖並填原因",
        ],
      },
    ],
  },
  {
    id: "claims",
    icon: "💰",
    title: "核銷案管理",
    href: "/claims",
    tagline: "打包諮商記錄，統一請款或收款",
    overview:
      "核銷案將多筆諮商記錄打包成一個核銷批次，適合機構月結請款或自費個案的期間收款確認。建立後可下載收據或請款單 PDF。",
    sections: [
      {
        type: "steps",
        heading: "建立自費核銷案",
        items: [
          "點「＋建立核銷案」，選「自費個案」",
          "搜尋並選擇個案",
          "勾選要納入的諮商記錄（系統列出尚未歸屬核銷案的記錄）",
          "設定期間（起訖日期）",
          "確認金額後建立",
          "狀態進入「收款中」，下載收據 PDF 後點「送出」→「結案」",
        ],
      },
      {
        type: "steps",
        heading: "建立機構核銷案",
        items: [
          "點「＋建立核銷案」，選「機構」",
          "選擇機構名稱",
          "勾選該機構的諮商記錄",
          "設定期間，確認建立",
          "等待心理師在「確認文件」頁面逐筆標記文件備妥",
          "全部確認後批次自動升為「文件備妥」",
          "行政點「提交請款」→ 填外部請款單號 → 等候到款",
          "款項到帳後點「標記到款」→「結案」，下載請款單 PDF 存檔",
        ],
      },
      {
        type: "flow",
        heading: "狀態流程",
        items: [
          "自費：收款中 → 送出 → 結案",
          "機構：收款中 → 文件備妥（自動）→ 已提交 → 款項到帳 → 結案",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "核銷案編號規則：自費 = S{週期碼}-{案號}-{YYYYMM}；機構 = I-{機構代碼}-{YYYYMM}",
          "同一筆諮商記錄不能同時屬於兩個核銷案",
          "PDF 收據格式：A4，含診所名稱、個案資訊、明細表、簽名欄",
        ],
      },
    ],
  },
  {
    id: "finance",
    icon: "💳",
    title: "財務管理",
    href: "/finance",
    tagline: "心理師酬勞月結與零用金管理",
    overview:
      "財務管理包含兩個子模組：心理師酬勞月結（依各人抽成比例自動計算）和零用金管理（診所日常支出記帳）。",
    sections: [
      {
        type: "steps",
        heading: "心理師酬勞月結",
        items: [
          "月底進入「財務管理」→「心理師酬勞」",
          "選擇年月",
          "點「產生月結」，系統依各心理師的抽成比例計算本月應付金額",
          "確認各心理師金額無誤",
          "逐一完成匯款後點「標記已付款」",
          "可匯出明細 CSV 作為薪資憑證",
        ],
      },
      {
        type: "steps",
        heading: "零用金管理",
        items: [
          "每筆支出點「＋新增支出」",
          "填入日期、金額、品項（如：打掃費、文具、水電費）",
          "系統即時更新零用金餘額",
          "餘額低於警戒線時系統顯示提示",
          "補款時記錄補款金額，水位恢復",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "各心理師抽成比例在「系統管理→帳號管理」設定，預設 70%",
          "月結計算基礎：當月所有已收款或請款中的諮商記錄",
          "若當月有調整抽成比例，系統使用諮商發生當下記錄的比例（commission_rate_used）",
        ],
      },
    ],
  },
  {
    id: "reports",
    icon: "📈",
    title: "營運報表",
    href: "/reports",
    tagline: "月度損益摘要與 KPI 追蹤",
    overview:
      "營運報表整合所有模組數據，自動產出月度損益摘要。管理層可即時掌握診所營收、心理師酬勞支出、零用金、淨收益與機構墊付狀況。",
    sections: [
      {
        type: "steps",
        heading: "查看月報表",
        items: [
          "進入「營運報表」",
          "選擇要查看的年月（預設當月）",
          "系統自動彙整：諮商總收入、心理師酬勞支出、診所場地費（30%）、零用金支出",
          "查看診所淨收益估算",
          "確認機構墊付金額（已執行但尚未收款的機構個案，診所墊付的 70% 部分）",
        ],
      },
      {
        type: "text",
        heading: "主要指標說明",
        items: [
          "諮商總收入：當月所有已執行諮商的費用總和",
          "心理師酬勞：依各人抽成比例計算的應付總額",
          "診所毛利（30%）：診所應得的場地與行政費用",
          "零用金支出：當月記錄的所有雜項支出",
          "淨收益：診所毛利 − 零用金支出",
          "目前墊付金額：機構未到款部分，診所暫付的心理師酬勞",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "報表數字即時反映帳冊狀態，帳冊有更新即反映在報表",
          "可匯出 CSV 供外部財務系統使用",
          "墊付金額越高代表機構款項積壓越多，需追蹤請款進度",
        ],
      },
    ],
  },
  {
    id: "admin",
    icon: "🔑",
    title: "系統管理",
    href: "/admin/users",
    tagline: "帳號管理、角色設定、機構維護",
    overview:
      "系統管理包含使用者帳號管理（邀請、停用）、角色與抽成比例設定，以及機構代碼維護。",
    sections: [
      {
        type: "steps",
        heading: "邀請新用戶",
        items: [
          "進入「系統管理 → 帳號管理」",
          "點「＋邀請用戶」",
          "填入對方的電子郵件",
          "選擇角色（管理員 / 行政人員 / 心理師）",
          "點「產生邀請碼」",
          "將邀請碼傳給對方（系統會顯示邀請連結）",
          "對方至登入頁點「首次註冊」輸入邀請碼完成註冊",
        ],
      },
      {
        type: "steps",
        heading: "設定心理師抽成比例",
        items: [
          "在帳號列表找到該心理師",
          "點「編輯」或「設定抽成」",
          "輸入抽成比例（例：0.70 代表 70%，範圍 0.01–0.99）",
          "儲存後新預約即採用新比例（歷史紀錄保留原比例快照）",
        ],
      },
      {
        type: "steps",
        heading: "管理機構資料",
        items: [
          "進入「帳號管理 → 機構」頁籤（或由側邊欄的機構管理）",
          "點「＋新增機構」",
          "填入機構全名與機構代碼（英數 5 碼，例：NTC01）",
          "機構代碼用於核銷案編號，設定後請勿修改",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "停用帳號後該用戶無法登入，但歷史諮商記錄與個案資料完整保留",
          "邀請碼可重複使用直到被人使用為止，請勿外洩",
          "管理員角色僅應授予診所負責人或主管行政，避免過度授權",
        ],
      },
      {
        type: "tips",
        heading: "注意事項",
        items: [
          "機構代碼一旦有核銷案使用後請勿修改，否則影響編號一致性",
          "抽成比例調整只影響未來新增的諮商，不會追溯修改已有記錄",
        ],
      },
    ],
  },
];

/* ───── helpers ───── */
function SectionBlock({ section }: { section: DocSection }) {
  if (section.type === "flow") {
    return (
      <div className="mb-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{section.heading}</h4>
        <div className="flex flex-wrap items-center gap-2">
          {section.items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm text-gray-700 shadow-sm">
                {item}
              </div>
              {i < section.items.length - 1 && <span className="text-gray-300">→</span>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (section.type === "steps") {
    return (
      <div className="mb-5">
        <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
          <span className="mr-1 text-primary-500">▶</span>{section.heading}
        </h4>
        <ol className="space-y-2">
          {section.items.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
                {i + 1}
              </span>
              <span className="text-sm text-gray-700">{item}</span>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  if (section.type === "tips") {
    return (
      <div className="mb-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          <span className="mr-1 text-amber-500">⚠</span>{section.heading}
        </h4>
        <ul className="space-y-2">
          {section.items.map((item, i) => (
            <li key={i} className="rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-sm text-amber-800">
              {item}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (section.type === "notes") {
    return (
      <div className="mb-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          <span className="mr-1">💡</span>{section.heading}
        </h4>
        <ul className="space-y-2">
          {section.items.map((item, i) => (
            <li key={i} className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-sm text-blue-800">
              {item}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="mb-5">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{section.heading}</h4>
      <ul className="space-y-1.5">
        {section.items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-300" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ───── main ───── */
export default function GuidePage() {
  const [activeId, setActiveId] = useState("overview");
  const active = modules.find((m) => m.id === activeId) ?? modules[0];

  return (
    <div className="flex h-[calc(100vh-64px)] overflow-hidden">
      {/* sidebar */}
      <nav className="hidden w-52 shrink-0 overflow-y-auto border-r border-gray-200 bg-gray-50 md:block">
        <div className="px-4 py-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">功能模組</p>
          <ul className="space-y-0.5">
            {modules.map((m) => (
              <li key={m.id}>
                <button
                  onClick={() => setActiveId(m.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                    activeId === m.id
                      ? "bg-primary-100 font-semibold text-primary-800"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  }`}
                >
                  <span className="mr-2">{m.icon}</span>
                  {m.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-gray-200 px-4 py-4">
          <p className="text-xs text-gray-400">管理員版說明</p>
          <p className="text-xs text-gray-400">CheerPsy v2</p>
        </div>
      </nav>

      {/* main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-6">
          {/* mobile module picker */}
          <div className="mb-5 md:hidden">
            <select
              value={activeId}
              onChange={(e) => setActiveId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              {modules.map((m) => (
                <option key={m.id} value={m.id}>{m.icon} {m.title}</option>
              ))}
            </select>
          </div>

          {/* module header */}
          <div className="mb-6 border-b border-gray-200 pb-5">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{active.icon}</span>
              <div>
                <h1 className="text-xl font-bold text-gray-900">{active.title}</h1>
                <p className="text-sm text-gray-500">{active.tagline}</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-gray-600">{active.overview}</p>
          </div>

          {/* sections */}
          <div>
            {active.sections.map((section, i) => (
              <SectionBlock key={i} section={section} />
            ))}
          </div>

          {/* nav buttons */}
          <div className="mt-8 flex items-center justify-between border-t border-gray-200 pt-5">
            {modules.findIndex((m) => m.id === activeId) > 0 ? (
              <button
                onClick={() => setActiveId(modules[modules.findIndex((m) => m.id === activeId) - 1].id)}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
              >
                ← {modules[modules.findIndex((m) => m.id === activeId) - 1].title}
              </button>
            ) : <div />}
            {modules.findIndex((m) => m.id === activeId) < modules.length - 1 ? (
              <button
                onClick={() => setActiveId(modules[modules.findIndex((m) => m.id === activeId) + 1].id)}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
              >
                {modules[modules.findIndex((m) => m.id === activeId) + 1].title} →
              </button>
            ) : <div />}
          </div>
        </div>
      </main>
    </div>
  );
}
