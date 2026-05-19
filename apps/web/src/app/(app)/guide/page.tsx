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
      "CheerPsy 以「預約驅動」為核心：建立個案 → 建立預約 → 預約結束時間一過，讀取帳冊即時自動入帳 → 在帳冊管理完成收款或機構請款 → 財務管理對帳、結算心理師酬勞與零用金 → 月底營運報表自動彙整。多數流程無需手動輸入。",
    sections: [
      {
        type: "flow",
        heading: "核心工作流程",
        items: [
          "建立個案",
          "建立預約",
          "預約結束自動入帳（帳冊流水帳）",
          "帳冊管理：收款 / 機構請款",
          "財務管理：對帳 / 酬勞 / 零用金",
          "營運報表",
        ],
      },
      {
        type: "text",
        heading: "角色與權限概覽",
        items: [
          "管理員：所有功能，含系統管理（帳號、機構、資料匯出入）與作廢、豁免等管理操作",
          "會計：財務報表與營運報表唯讀；不可建立個案、預約",
          "行政人員：個案、預約、帳冊收款、機構請款、商品販售、財務管理（不含系統管理）",
          "心理師：僅本人預約與帳冊；可建立/取消自己的預約、確認機構文件、作廢當日本人紀錄",
          "全角色：個人設定可修改自己的 Email、密碼（心理師另可設預設價格）",
        ],
      },
      {
        type: "tips",
        heading: "重要規則",
        items: [
          "即時結算：預約結束時間一過，讀取「帳冊流水帳」時系統自動產生該筆紀錄；不需手動日結（仍保留「執行日結」按鈕供補登）",
          "70/30 拆帳：以實收金額（折扣後、排除作廢）依各心理師抽成比例快照自動計算",
          "個案未到請於當日內取消預約，否則時間一過將自動入帳；如已入帳可改用「作廢」處理",
          "機構墊付：機構個案先付心理師，機構到款前由診所墊付，財務管理與月報表追蹤墊付金額",
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
      "個案管理採兩階段設計：預約時只需填基本資料並指定心理師（Stage 1），初診到場後補填關鍵資料並「轉正式」產生永久案號（Stage 2）。",
    sections: [
      {
        type: "steps",
        heading: "Stage 1：新增預約個案",
        items: [
          "點「＋新增個案」",
          "填入姓名、電話、年齡（估算用即可）",
          "指定負責心理師",
          "選付費方式（自費 / 機構），機構需選對應機構名稱",
          "選結帳週期（單次 / 月結 / 多次）",
          "儲存後狀態為「已預約未初談」，系統自動分配流水序號 #000X",
        ],
      },
      {
        type: "steps",
        heading: "Stage 2：初診後轉為正式個案",
        items: [
          "個案初診到場後，點個案列表展開的詳情面板「編輯」",
          "補填轉正式三項必填：身份證字號、出生日期、電話（姓名與心理師已於建立時設定）",
          "可選填地址、市話、緊急聯絡人、轉介來源、會談地點、初談日期",
          "儲存後點「轉正式」",
          "系統自動產生 8 碼正式案號（例：26000145）",
          "狀態自動變為「進行中」",
        ],
      },
      {
        type: "text",
        heading: "狀態流程",
        items: [
          "已預約未初談 → 轉正式後變為「進行中」",
          "進行中 → 可手動改為「暫停」「結案」或「流失」",
          "編輯時狀態下拉不顯示「已預約未初談」（僅能由新增產生）",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "身份證字號以加密儲存，列表不顯示原始值",
          "轉正式後案號不可修改，請確認再按",
          "個案詳情面板可直接快速建立預約",
        ],
      },
      {
        type: "tips",
        heading: "注意事項",
        items: [
          "機構個案請務必選對機構，影響機構請款流程",
          "結帳週期「月結」代表月底統一出帳，請與個案實際付費方式一致",
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
      "所有諮商都從預約開始。預約建立後，當其結束時間一過，下次讀取「帳冊流水帳」時系統自動入帳，無需手動操作。",
    sections: [
      {
        type: "steps",
        heading: "新增單次預約",
        items: [
          "點「＋新增預約」（或在月曆空格點擊）",
          "選個案（可輸入姓名搜尋）",
          "選心理師、諮商類型（現場 / 線上 / 家訪）、診間",
          "選日期、起始時間（預設 50 分鐘）",
          "金額自動帶入該心理師的預設價格，可手動調整",
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
          "系統產生排程並顯示預覽清單",
          "確認後一次建立所有預約",
        ],
      },
      {
        type: "steps",
        heading: "取消預約",
        items: [
          "在月曆或預約列表找到該筆預約",
          "點「取消」並確認",
          "當日取消不計費；若結束時間已過並入帳，請改至帳冊「作廢」",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "金額預設值由心理師「個人設定」的預設價格決定，可在預約時覆寫",
          "診間衝突由系統自動阻擋（PostgreSQL EXCLUDE GIST），同診間同時段無法重複預約",
        ],
      },
    ],
  },
  {
    id: "ledger",
    icon: "📒",
    title: "帳冊流水帳",
    href: "/ledger",
    tagline: "即時入帳的諮商財務流水帳",
    overview:
      "帳冊流水帳為唯讀流水帳：預約結束時間一過，讀取本頁即自動產生紀錄（即時結算）。每筆有收據編號（R{YYYYMMDD}{序號}），支援優待/折扣與作廢，並可列印收據。",
    sections: [
      {
        type: "steps",
        heading: "即時結算與補登",
        items: [
          "進入帳冊流水帳，系統自動將已結束的預約入帳",
          "確認新增的紀錄與收據編號（格式 R{YYYYMMDD}{序號}）",
          "若需補跑歷史日期，點「執行日結」並選日期區間（補登用）",
        ],
      },
      {
        type: "steps",
        heading: "優待 / 折扣",
        items: [
          "找到該筆紀錄，點調整折扣",
          "輸入優待或折扣金額",
          "系統以實收金額（原價 − 折扣）重新計算拆帳",
        ],
      },
      {
        type: "steps",
        heading: "作廢紀錄",
        items: [
          "找到誤產生或不應計費的紀錄，點「作廢」",
          "管理員 / 行政可作廢任一筆；心理師僅可作廢本人當日紀錄",
          "作廢後不計入收款、報表與酬勞，且不可復原",
        ],
      },
      {
        type: "steps",
        heading: "列印收據",
        items: [
          "找到欲開立收據的紀錄",
          "點「列印收據」產生收據（顯示收據編號與實收金額）",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "「待處理」分頁列出尚未收款 / 請款的紀錄；作廢紀錄不列入",
          "本頁為唯讀流水帳，不再有鎖定 / 解鎖；收款狀態由帳冊管理流程自動更新",
          "可依心理師、月份、付費方式、收款狀態篩選",
        ],
      },
    ],
  },
  {
    id: "claims",
    icon: "💰",
    title: "帳冊管理",
    href: "/claims",
    tagline: "自費收款與機構請款的集中處理",
    overview:
      "帳冊管理分兩個分頁：自費（依個案手風琴展開，勾選紀錄後付款，免建核銷批次）與機構（機構請款批次，含文件繳交與生命週期）。",
    sections: [
      {
        type: "steps",
        heading: "自費收款",
        items: [
          "切到「自費」分頁，找到該個案手風琴並展開",
          "勾選要收款的紀錄",
          "點「付款」開啟付款 modal",
          "選付款方式（現金 / 匯款）",
          "可補登實際收款日期",
          "選收據型式：合併單張或逐筆收據",
          "確認後該批紀錄標記為已收款（不需建立核銷批次）",
        ],
      },
      {
        type: "steps",
        heading: "機構請款批次",
        items: [
          "切到「機構」分頁，建立機構請款批次並勾選紀錄",
          "心理師 / 行政 / 管理員逐筆確認文件繳交（心理師確認後無法自行取消確認）",
          "管理員 / 行政可「豁免本案資料」，或將整個機構設為「免繳資料」",
          "文件齊備後批次自動進入 ready",
          "行政點提交（submitted）→ 機構到款（received）→ 結案（closed）",
        ],
      },
      {
        type: "flow",
        heading: "機構批次狀態流程",
        items: [
          "collecting 收集中",
          "ready 文件備妥",
          "submitted 已提交",
          "received 已到款",
          "closed 結案",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "自費不需核銷批次，直接在分頁勾選 + 付款 modal 完成",
          "「免繳資料」機構的批次不需心理師繳交文件即可推進",
          "心理師可確認文件但無法取消已確認的狀態，避免事後竄改",
        ],
      },
    ],
  },
  {
    id: "finance",
    icon: "💳",
    title: "財務管理",
    href: "/finance",
    tagline: "款項追蹤、心理師酬勞月結與零用金",
    overview:
      "財務管理含三個分頁：款項追蹤（機構 / 自費子分頁與每日對帳）、心理師酬勞（月結）、零用金。",
    sections: [
      {
        type: "steps",
        heading: "款項追蹤",
        items: [
          "進入「款項追蹤」分頁",
          "「機構」子分頁：以進度條顯示各機構請款進度，並有每日對帳",
          "每日對帳可依付款方式篩選（現金 / 匯款 / 全部）",
          "「自費」子分頁：依個案手風琴顯示點狀進度（已結清 / 待收）",
        ],
      },
      {
        type: "steps",
        heading: "心理師酬勞月結",
        items: [
          "進入「心理師酬勞」分頁，選擇年月",
          "點「產生月結」，系統依抽成比例與實收金額計算應付金額",
          "確認各心理師金額（可重複產生，已付款者不重算）",
          "逐一完成匯款後點「標記已付款」",
        ],
      },
      {
        type: "steps",
        heading: "零用金管理",
        items: [
          "進入「零用金」分頁，點「＋新增支出」",
          "填入日期、金額、品項（如打掃費、文具、水電費）",
          "系統即時更新餘額，餘額偏低時顯示提示",
          "補款時記錄補款金額，水位恢復",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "各心理師抽成比例於「系統管理 → 帳號管理」設定，預設 70%",
          "月結以實收金額（折扣後、排除作廢）為基礎",
          "若當月調整抽成，系統採諮商發生當下的比例快照（commission_rate_used）",
        ],
      },
    ],
  },
  {
    id: "products",
    icon: "🛒",
    title: "商品販售",
    href: "/products",
    tagline: "非諮商商品 / 品項銷售記錄",
    overview:
      "商品販售用於記錄非諮商的商品或品項銷售（如書籍、教材、講座費）。每筆自動產生收據編號 P{YYYYMMDD}{序號}，支援作廢，並於月報表獨立統計。",
    sections: [
      {
        type: "steps",
        heading: "新增商品銷售",
        items: [
          "進入「商品販售」（管理員 / 會計 / 行政可使用）",
          "點「＋新增銷售」",
          "填入品項、金額、日期等資訊",
          "儲存後系統自動產生收據編號 P{YYYYMMDD}{序號}",
        ],
      },
      {
        type: "steps",
        heading: "作廢銷售紀錄",
        items: [
          "找到誤建或退貨的紀錄",
          "點「作廢」並確認",
          "作廢後不計入報表收入",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "商品銷售與諮商帳冊獨立，於營運報表「其他商品販售」區塊單獨呈現",
          "心理師無此頁面權限",
        ],
      },
    ],
  },
  {
    id: "reports",
    icon: "📈",
    title: "營運報表",
    href: "/reports",
    tagline: "月度損益摘要與流失警示",
    overview:
      "營運報表整合各模組數據，自動產出月度損益摘要。收入以實收金額（金額 − 折扣、排除作廢）計算，並獨立統計商品販售與流失警示。",
    sections: [
      {
        type: "steps",
        heading: "查看月報表",
        items: [
          "進入「營運報表」（管理員 / 會計可使用）",
          "選擇年月（預設當月）",
          "系統彙整：諮商實收總收入、心理師酬勞、診所毛利（30%）、零用金支出",
          "查看「其他商品販售」區塊",
          "查看診所淨收益與機構墊付金額",
        ],
      },
      {
        type: "text",
        heading: "主要指標說明",
        items: [
          "諮商總收入：當月實收金額（金額 − 折扣、排除作廢）",
          "心理師酬勞：依各人抽成比例與實收金額計算的應付總額",
          "診所毛利（30%）：診所應得的場地與行政費用",
          "其他商品販售：商品販售模組當月收入（不含作廢）",
          "零用金支出：當月記錄的所有雜項支出",
          "淨收益：診所毛利 + 商品販售 − 零用金支出",
          "目前墊付金額：機構未到款部分，診所暫付的心理師酬勞",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "報表即時反映帳冊狀態，作廢與折扣會即時排除 / 扣除",
          "流失警示列出近期無新預約、可能流失的個案，需追蹤",
          "墊付金額越高代表機構款項積壓越多，需追蹤請款進度",
        ],
      },
    ],
  },
  {
    id: "settings",
    icon: "⚙️",
    title: "個人設定",
    href: "/settings",
    tagline: "管理自己的帳號與預設價格",
    overview:
      "所有角色皆可在個人設定維護自己的帳號資料：變更 Email、變更密碼；心理師另可設定預設價格，建立預約時自動帶入。",
    sections: [
      {
        type: "steps",
        heading: "變更 Email",
        items: [
          "進入「個人設定」",
          "輸入新的 Email",
          "儲存後以新 Email 登入",
        ],
      },
      {
        type: "steps",
        heading: "變更密碼",
        items: [
          "進入「個人設定」的密碼區塊",
          "輸入目前密碼以驗證身分",
          "輸入新密碼並確認",
          "儲存後立即生效",
        ],
      },
      {
        type: "steps",
        heading: "設定預設價格（心理師）",
        items: [
          "心理師在「個人設定」找到預設價格欄位",
          "輸入常用諮商費用",
          "儲存後，建立預約時金額自動帶入此值（仍可逐筆覆寫）",
        ],
      },
      {
        type: "notes",
        heading: "提示",
        items: [
          "變更密碼必須通過目前密碼驗證，避免遭他人擅改",
          "預設價格僅影響新預約預填值，不影響既有紀錄",
        ],
      },
    ],
  },
  {
    id: "admin",
    icon: "🔑",
    title: "系統管理",
    href: "/admin",
    tagline: "帳號管理、機構管理、資料匯出入",
    overview:
      "系統管理（僅管理員）含三個分頁：帳號管理（邀請各角色、抽成與預設價格）、機構管理（含免繳資料設定）、資料匯出入（全資料表 CSV 匯出與三模式匯入）。",
    sections: [
      {
        type: "steps",
        heading: "帳號管理",
        items: [
          "進入「系統管理 → 帳號管理」",
          "點「＋邀請用戶」，填 Email、選角色（管理員 / 會計 / 行政 / 心理師）",
          "系統自動產生 user_code（依角色 A / C / S / T 前綴）",
          "把邀請連結交給對方，對方憑此完成首次註冊",
          "在列表可就地編輯心理師的抽成比例與預設價格",
        ],
      },
      {
        type: "steps",
        heading: "機構管理",
        items: [
          "進入「機構管理」分頁，點「＋新增機構」",
          "填入機構全名與 5 碼機構代碼（例：NTC01）",
          "視情況開啟 / 關閉「需心理師繳交資料」",
          "關閉者為「免繳資料」機構，其請款批次不需心理師繳交文件",
        ],
      },
      {
        type: "steps",
        heading: "資料匯出入",
        items: [
          "進入「資料匯出入」分頁",
          "匯出：可將所有資料表（含全欄位）匯出為 CSV",
          "匯入先選模式：🔍除錯模式（試跑驗證、不寫入）",
          "➕補登（僅新增不存在的 id，不覆蓋既有資料）",
          "⚠️清洗覆蓋（upsert，會覆蓋既有資料，需輸入管理員密碼）",
          "系統回報每列的錯誤與警告，確認後再正式匯入",
        ],
      },
      {
        type: "tips",
        heading: "注意事項",
        items: [
          "user_code 由系統自動產生，不需手動指定；停用帳號後仍保留歷史資料",
          "機構代碼經請款使用後請勿修改，以維持編號一致",
          "「⚠️清洗覆蓋」會覆寫資料且需管理員密碼，務必先以除錯模式驗證",
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
