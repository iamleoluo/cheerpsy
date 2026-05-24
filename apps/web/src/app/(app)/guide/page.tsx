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
          "即時結算：預約結束時間一過，讀取「帳冊流水帳」時系統即時產生該筆紀錄；不需手動日結（仍保留「執行日結」按鈕供補登歷史日期）",
          "師所拆帳：以實收金額（折扣後、排除作廢）依各心理師抽成比例快照自動計算，預設 70% 師 / 30% 所",
          "個案未到請於當日內取消預約，否則時間一過將自動入帳；如已入帳可改用「作廢」處理",
          "機構待請款：機構個案的心理師酬勞由診所先行墊付，機構到款後才算回收；金流來源分析與月報表可追蹤機構待請款金額",
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
      "個案管理採兩階段設計：預約時只需填基本資料並指定心理師（Stage 1），初診到場後補填關鍵資料並「轉正式」產生永久案號（Stage 2）。另有「預約總表」與「機構額度」兩個分頁。",
    sections: [
      {
        type: "steps",
        heading: "Stage 1：新增預約個案",
        items: [
          "點「＋新增個案」",
          "填入姓名、電話、年齡（估算用即可）",
          "指定負責心理師",
          "選結帳週期（次結 / 月結 / 多次結）",
          "儲存後狀態為「已預約未初談」，系統自動分配流水序號 #000X",
          "所有個案預設為自費；若有機構額度，請於「機構額度」分頁另行新增",
        ],
      },
      {
        type: "steps",
        heading: "Stage 2：初診後轉為正式個案",
        items: [
          "個案初診到場後，點個案列表展開的詳情面板「編輯」",
          "補填轉正式三項必填：身份證字號、出生日期、電話",
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
        ],
      },
      {
        type: "steps",
        heading: "機構額度管理",
        items: [
          "切換至「機構額度」分頁，內有兩個子分頁：「額度管理」與「方案範本」",
          "【額度管理】列表依個案分組：每列顯示總已用 / 總額度、剩餘、機構數與狀態概覽",
          "點 ▶ 展開後顯示各機構的明細（有效期、剩餘次數、狀態）與編輯 / 刪除按鈕",
          "點列右側「＋新增」可快速為該個案新增額度，或點右上角「＋新增 Quota」從頭填寫",
          "狀態「預約鎖定」代表剩餘 0 但有預約中尚未結算的次數",
          "【方案範本】可預先定義常用方案（如：某機構的「青壯方案 8 次」），範本依機構分組顯示",
          "建立範本後點「套用」，選擇個案（可多選）並設定有效起迄日，一鍵批次建立額度",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "身份證字號以加密儲存，列表不顯示原始值",
          "轉正式後案號不可修改，請確認再按",
          "個案詳情面板可直接快速建立預約；「預約總表」分頁可跨個案查看所有預約",
        ],
      },
      {
        type: "tips",
        heading: "注意事項",
        items: [
          "機構額度請在「機構額度」分頁新增，並確認機構與有效期間正確，影響後續請款流程",
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
      "所有諮商都從預約開始。預約建立後，當其結束時間一過，系統自動入帳，無需手動操作。日曆有三個分頁：診間日曆（空間）以 FullCalendar 顯示；診間日曆（時段）以診間為欄位、時段為列的表格顯示空間使用狀況；預約提醒用於電訪追蹤。",
    sections: [
      {
        type: "steps",
        heading: "新增單次預約",
        items: [
          "點「＋新增預約」（或在月曆空格點擊）",
          "選個案（可輸入姓名搜尋）",
          "選心理師、諮商類型（現場 / 線上 / 外出）",
          "現場類型需選診間；線上 / 外出不需選診間",
          "選日期、起始時間（預設 50 分鐘），填入費用",
          "機構個案需選對應的機構額度（Quota）",
          "儲存",
        ],
      },
      {
        type: "steps",
        heading: "批次預約（定期諮商）",
        items: [
          "點「批次預約」",
          "選個案、心理師、類型、診間",
          "設定起始日期、頻率（每週 / 每兩週 / 每月）、總次數",
          "系統產生排程並顯示預覽清單，可確認各場次日期",
          "確認後一次建立所有預約",
        ],
      },
      {
        type: "steps",
        heading: "編輯已建立的預約",
        items: [
          "在個案管理詳情面板或個案管理「預約總表」找到該筆 booked 預約",
          "點「編輯」開啟編輯表單",
          "可修改：類型、診間、日期時間、費用、付費方式、機構額度",
          "個案與心理師不可修改",
          "系統自動檢查診間衝突（排除自身）後儲存",
        ],
      },
      {
        type: "steps",
        heading: "取消預約",
        items: [
          "在月曆或預約列表找到該筆預約",
          "點「取消」並確認",
          "當日取消不計費；若結束時間已過並已入帳，請改至帳冊「作廢」",
        ],
      },
      {
        type: "text",
        heading: "診間時段檢視（空間使用）",
        items: [
          "切換至「診間日曆（時段）」分頁",
          "縱軸為時段（09:00 ～ 19:30，每 30 分鐘一格），橫軸為各診間",
          "有預約的格子顯示心理師姓名（藍底）；空格為閒置",
          "點格子可看預約編號與時間區間",
          "上方可切換日期或選取特定日期，快速確認診間空閒狀況",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "金額預設值由心理師「個人設定」的預設價格決定，可在預約時覆寫",
          "診間衝突由系統自動阻擋，同診間同時段無法重複預約",
          "外出保底費用不依診間計算，請在費用欄手動輸入保底金額",
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
      "帳冊流水帳為唯讀流水帳：預約結束時間一過，讀取本頁即自動產生紀錄（即時結算）。每筆有收據編號，支援優待 / 折扣、作廢、拆帳與收據開立。「來源」欄顯示機構名稱或自費結算方式，一眼辨認付費方。",
    sections: [
      {
        type: "steps",
        heading: "即時結算與補登",
        items: [
          "進入帳冊流水帳，系統自動將已結束的預約入帳",
          "確認新增的紀錄，來源欄顯示「機構（XXX基金會）」或「自費（月結）」",
          "若需補跑歷史日期，點「執行日結」並選日期區間（補登用）",
        ],
      },
      {
        type: "steps",
        heading: "優待 / 折扣",
        items: [
          "找到該筆紀錄，點「調整折扣」",
          "輸入優待或折扣金額",
          "系統以實收金額（原價 − 折扣）重新計算拆帳",
        ],
      },
      {
        type: "steps",
        heading: "拆帳（機構 + 自費混付）",
        items: [
          "機構個案如需自費補差額，點「拆帳」",
          "填入自費部分金額、付款方式",
          "可自訂費用名稱（收據顯示，預設「行政規費」）",
          "確認後產生一筆自費子紀錄，與機構部分獨立計算",
        ],
      },
      {
        type: "steps",
        heading: "開立收據",
        items: [
          "自費（無批次）：找到已收款紀錄，點「開立收據」產生單次收據 PDF",
          "自費（有批次）：已結清的批次紀錄顯示「整體收據」，點擊產生多次整體收據 PDF",
          "機構：已歸入核銷案的紀錄顯示「核銷案收據」連結，點擊跳至帳冊管理查看",
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
        type: "notes",
        heading: "管理員提示",
        items: [
          "「待處理」分頁列出尚未收款 / 請款的紀錄；作廢紀錄不列入",
          "本頁為唯讀流水帳；收款狀態由帳冊管理流程自動更新",
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
      "帳冊管理分兩個分頁：自費（依個案手風琴展開，勾選紀錄後付款，免建核銷批次）與機構（機構請款批次，含文件繳交與生命週期）。文件確認功能僅適用機構個案，自費個案不需繳交文件。",
    sections: [
      {
        type: "steps",
        heading: "自費收款",
        items: [
          "切到「自費」分頁，找到該個案手風琴並展開",
          "勾選要收款的紀錄（可全選）",
          "點「付款」開啟付款 modal",
          "選付款方式（現金 / 匯款）、可填付款備註",
          "確認後該批紀錄標記為已收款，並可回到帳冊流水帳開立整體收據",
        ],
      },
      {
        type: "steps",
        heading: "機構請款批次",
        items: [
          "切到「機構」分頁，點「＋新增核銷案」",
          "選擇機構與個案，勾選要納入的帳冊紀錄",
          "心理師在「文件確認」分頁逐筆確認文件已繳交（確認後不可自行取消）",
          "管理員 / 行政可「豁免本案資料」，或設機構為「免繳資料」跳過文件確認",
          "所有文件齊備後批次自動進入 ready（文件備妥）",
          "行政點「提交」（submitted）→ 機構到款後點「到款」（received，終態）",
        ],
      },
      {
        type: "flow",
        heading: "機構批次狀態流程",
        items: [
          "collecting 收集中",
          "ready 文件備妥",
          "submitted 已提交",
          "received 已到款（終態）",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "自費不需建核銷批次，直接在分頁勾選 + 付款 modal 完成收款",
          "文件確認分頁只顯示機構個案紀錄；自費個案不出現在文件確認清單",
          "「免繳資料」機構的批次不需心理師繳交文件即可推進至 ready",
          "心理師只能確認、不能取消確認，避免事後竄改；行政 / 管理員可撤回",
        ],
      },
    ],
  },
  {
    id: "finance",
    icon: "💳",
    title: "財務管理",
    href: "/finance",
    tagline: "款項追蹤、心理師酬勞與零用金",
    overview:
      "財務管理含三個分頁：款項追蹤（機構 / 自費子分頁，右側有每日對帳面板）、心理師酬勞（依月份產生酬勞清單）、零用金（雜項支出記錄）。",
    sections: [
      {
        type: "steps",
        heading: "款項追蹤",
        items: [
          "進入「款項追蹤」分頁，預設顯示「機構」子分頁",
          "機構子分頁：列出各機構核銷批次，顯示狀態時間軸（建立→提交→結案）與批次金額",
          "右側「每日對帳」面板：選日期，可依全部 / 現金 / 匯款篩選，列出當日自費與機構明細",
          "切換「自費」子分頁：依個案分組顯示已結清 / 待收紀錄",
        ],
      },
      {
        type: "steps",
        heading: "心理師酬勞",
        items: [
          "進入「心理師酬勞」分頁，選擇年月",
          "點「產生酬勞」，系統依各心理師抽成比例與當月實收金額計算應付金額",
          "列表顯示月份、心理師、場次、酬勞金額、狀態、發放日期",
          "確認後逐一完成匯款，點「標記已付款」更新狀態",
          "可重複產生，已標記付款者不重算",
        ],
      },
      {
        type: "steps",
        heading: "零用金管理",
        items: [
          "進入「零用金」分頁，目前餘額顯示於頁首",
          "點「＋新增紀錄」，填入日期、類別、說明、金額、收據備註",
          "系統即時更新餘額欄位",
          "可點「匯出 CSV」匯出所有零用金紀錄",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "各心理師抽成比例於「系統管理 → 帳號管理」就地編輯，預設 70%",
          "酬勞以實收金額（折扣後、排除作廢）為基礎，採諮商發生當下的比例快照",
          "若當月調整抽成，歷史已入帳紀錄不受影響",
        ],
      },
    ],
  },
  {
    id: "products",
    icon: "🛒",
    title: "商品販售",
    href: "/products",
    tagline: "非諮商品項銷售記錄",
    overview:
      "商品販售用於記錄非諮商的品項銷售（如書籍、教材、講座費）。每筆自動產生收據編號 P{YYYYMMDD}{序號}，可開立收據 PDF，支援作廢，並於月報表獨立統計。",
    sections: [
      {
        type: "steps",
        heading: "新增銷售",
        items: [
          "進入「商品販售」（管理員 / 行政可使用）",
          "點「＋新增銷售」",
          "填入品名、單價、數量、日期、付款方式",
          "儲存後系統自動產生收據編號 P{YYYYMMDD}{序號}",
        ],
      },
      {
        type: "steps",
        heading: "開立收據 / 作廢",
        items: [
          "每筆右側點「開立收據」可產生 PDF 收據",
          "如需作廢：點「作廢」並確認，作廢後不計入報表收入",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "商品銷售與諮商帳冊獨立，於營運報表「其他商品販售」區塊單獨呈現",
          "心理師無此頁面權限；會計可唯讀查看",
        ],
      },
    ],
  },
  {
    id: "reports",
    icon: "📈",
    title: "營運報表",
    href: "/reports",
    tagline: "月度損益摘要與流失預警",
    overview:
      "營運報表含兩個分頁：月報表（損益摘要、KPI 指標、諮商類型分布、金流來源分析、其他商品販售）與流失預警（近期無新預約個案清單）。收入以實收金額（金額 − 折扣、排除作廢）計算。",
    sections: [
      {
        type: "steps",
        heading: "查看月報表",
        items: [
          "進入「營運報表」（管理員 / 會計可使用）",
          "選擇年份與月份，點「產生報表」",
          "上方摘要卡片：總營收、諮商次數、心理師分費、診所收入、已收 / 請款數、未收 / 請款數、零用金支出、取消預約數",
          "損益摘要：總營收 − 心理師成本 = 診所毛利；診所毛利 − 零用金 = 淨收入",
          "金流來源分析：自費收入 / 機構收入 / 機構待請款（尚未到款的機構金額）",
          "可點「匯出 CSV」匯出當月數據",
        ],
      },
      {
        type: "text",
        heading: "主要指標說明",
        items: [
          "總營收：當月實收金額（金額 − 折扣、排除作廢）",
          "心理師分費：依各人抽成比例與實收金額計算的應付總額",
          "診所收入：診所應得的場地與行政費用（總營收 − 心理師分費）",
          "其他商品販售：商品販售模組當月收入（不含作廢）",
          "零用金支出：當月記錄的所有雜項支出",
          "淨收入：診所收入 + 商品販售 − 零用金支出",
          "機構待請款：機構尚未到款部分，代表診所仍在墊付的金額",
        ],
      },
      {
        type: "steps",
        heading: "流失預警",
        items: [
          "切換至「流失預警」分頁",
          "列出近期無新預約、可能流失的個案清單",
          "顯示個案姓名、最後預約日期、負責心理師",
          "可直接點擊跳至個案管理追蹤",
        ],
      },
      {
        type: "notes",
        heading: "管理員提示",
        items: [
          "報表即時反映帳冊狀態，作廢與折扣即時排除 / 扣除，不需重新產生",
          "機構待請款越高代表機構款項積壓越多，需追蹤帳冊管理的請款進度",
          "KPI 指標顯示取消率、續診率、活躍心理師數、本月個案數",
        ],
      },
    ],
  },
  {
    id: "settings",
    icon: "⚙️",
    title: "個人設定",
    href: "/settings",
    tagline: "管理自己的帳號資料與預設價格",
    overview:
      "所有角色皆可在個人設定維護自己的帳號資料。頁面顯示姓名與角色（唯讀），可修改登入 Email 與密碼；任何變更都必須輸入目前密碼確認。心理師另可設定預設諮商價格。",
    sections: [
      {
        type: "steps",
        heading: "變更 Email 或密碼",
        items: [
          "進入「個人設定」",
          "修改登入 Email（僅需覆寫，留空則不變）",
          "如需改密碼：填入新密碼與確認新密碼（留空則不變）",
          "任何變更都必須在「目前密碼」欄輸入現有密碼",
          "點「儲存變更」，Email 與密碼同時生效",
        ],
      },
      {
        type: "steps",
        heading: "設定預設價格（心理師）",
        items: [
          "心理師在個人設定頁面可看到「預設諮商價格」欄位",
          "輸入常用諮商費用並儲存",
          "之後建立預約時，金額欄位自動帶入此值（仍可逐筆覆寫）",
        ],
      },
      {
        type: "notes",
        heading: "提示",
        items: [
          "姓名與角色由管理員在帳號管理設定，個人設定頁不可自行修改",
          "預設價格僅影響新預約的預填值，已建立的預約金額不受影響",
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
      "系統管理（僅管理員）含三個分頁：帳號管理（建立邀請、設定抽成比例與預設價格）、機構管理（含免繳資料設定）、資料匯出入（全資料表 CSV 匯出與三模式匯入）。",
    sections: [
      {
        type: "steps",
        heading: "帳號管理",
        items: [
          "進入「系統管理 → 帳號管理」",
          "點「＋建立邀請」，填 Email、選角色（管理員 / 會計 / 行政 / 心理師）",
          "系統自動產生代號（依角色 A / C / S / T 前綴，如 T004）",
          "將邀請連結交給對方，對方憑此完成首次設定密碼",
          "帳號列表顯示姓名、Email、角色、代號、抽成比例、預設價格、狀態",
          "可就地點「編輯」調整心理師的抽成比例與預設價格；「停用」保留歷史資料但阻擋登入",
        ],
      },
      {
        type: "steps",
        heading: "機構管理",
        items: [
          "進入「機構管理」分頁，點「＋新增機構」",
          "填入機構全名與 5 碼機構代碼（例：EDU01）",
          "視情況開啟 / 關閉「需心理師繳交資料」",
          "關閉者為「免繳資料」機構，其請款批次不需心理師確認文件即可推進",
        ],
      },
      {
        type: "steps",
        heading: "資料匯出入",
        items: [
          "進入「資料匯出入」分頁",
          "匯出：可將所有資料表（含全欄位）匯出為 CSV，包含個案、預約、帳冊、核銷案、機構、方案範本等",
          "匯入先選模式：🔍 除錯模式（試跑驗證、不寫入資料庫）",
          "➕ 補登模式（僅新增不存在的 id，不覆蓋既有資料）",
          "⚠️ 清洗覆蓋（upsert，會覆寫既有資料，需輸入管理員密碼確認）",
          "系統回報每列的錯誤與警告，確認無誤後再正式匯入",
        ],
      },
      {
        type: "tips",
        heading: "注意事項",
        items: [
          "代號由系統自動產生，不需手動指定；停用帳號後仍保留歷史諮商與帳務資料",
          "機構代碼一旦有請款批次使用後請勿修改，以維持批次編號一致",
          "「⚠️ 清洗覆蓋」不可復原，務必先以除錯模式驗證再執行",
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
  const [activeId, setActiveId] = useState(() => {
    if (typeof window !== "undefined") {
      const hash = window.location.hash.slice(1);
      if (hash && modules.find((m) => m.id === hash)) return hash;
    }
    return "overview";
  });
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
