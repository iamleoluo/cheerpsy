"use client";

const modules = [
  {
    id: "01",
    title: "個案管理",
    href: "/cases",
    icon: "👤",
    desc: "儲存個案基本資料，包含聯絡方式、經費來源、負責心理師等。初診時建立，基本資料不頻繁異動。",
    steps: [
      "點選「個案管理」→「＋新增個案」",
      "填入姓名、性別、出生日期、聯絡電話等資料",
      "選擇經費來源：自費 或 機構轉介",
      "機構轉介需選擇對應機構",
      "指定負責心理師後儲存",
    ],
    roles: "全角色均可查看；新增／編輯限行政與管理員",
  },
  {
    id: "02",
    title: "預約管理",
    href: "/appointments",
    icon: "📅",
    desc: "系統動態核心。心理師建立預約後，系統依狀態自動驅動流水帳、空間佔用與金流追蹤，無需手動介入。",
    steps: [
      "點選「預約管理」→「＋新增預約」或「批次預約」",
      "選個案、諮商類型（現場／線上／家訪）、空間",
      "填入日期、時段、金額（70/30 抽成自動計算）",
      "系統隔日結算：前一日未取消的預約自動進入流水帳",
      "若個案未到，請於當日內點「取消」，逾時視為已執行",
    ],
    roles: "所有角色均可操作；修改已發生紀錄限管理員",
  },
  {
    id: "03",
    title: "諮商流水帳",
    href: "/ledger",
    icon: "📒",
    desc: "由預約「已執行」後自動寫入，無需手動輸入。每筆紀錄包含諮商日期、個案、心理師、費用與 70/30 拆分金額。",
    steps: [
      "流水帳由系統自動產生，不需手動新增",
      "行政可在此更新收款狀態（已收款／未收款）",
      "可依心理師、日期區間、收款狀態篩選",
      "管理員可匯出 CSV 進行對帳",
      "管理員每日點「執行日結（每日查看請點擊確保資料更新）」更新資料；若需補跑過去某段期間，選擇日期區間後再點擊",
    ],
    roles: "心理師僅看個人紀錄；行政與管理員可看全所",
  },
  {
    id: "04",
    title: "空間預約",
    href: "/rooms",
    icon: "🏢",
    desc: "即時空間佔用表，與預約系統連動。建立實體預約時自動佔位，取消時自動釋出。僅適用實體諮商。",
    steps: [
      "進入「空間預約」查看各診間當週時段表",
      "點選週曆左右切換週次，或切換月視圖",
      "格子顯示心理師姓名表示已佔用，空白表示可預約",
      "點選個別空間切換查看該診間排程",
    ],
    roles: "全角色均可查看",
  },
  {
    id: "05",
    title: "財務核銷",
    href: "/reconciliation",
    icon: "💰",
    desc: "追蹤所有個案的付款與請款狀態。自費個案進入待收款清單；機構個案進入請款池，累積後批次請款。",
    steps: [
      "自費個案：確認收到款項後，點選對應紀錄標記「已收款」",
      "機構個案：累積後點「批次請款」，填入請款單號",
      "到帳後更新為「已核銷」",
      "可依機構、狀態、日期篩選",
    ],
    roles: "限行政與管理員",
  },
  {
    id: "06",
    title: "心理師酬勞",
    href: "/payouts",
    icon: "💳",
    desc: "月結管理心理師 70% 酬勞。系統自動依流水帳計算每月應付金額，行政逐一確認付款後標記。",
    steps: [
      "每月月結時進入「心理師酬勞」，選擇年月",
      "點「產生月結」，系統依流水帳自動計算各心理師應付金額（可重複點擊以更新）",
      "逐一完成付款後點「標記已付款」",
      "可匯出明細作為薪資憑證",
    ],
    roles: "限行政與管理員",
  },
  {
    id: "07",
    title: "零用金",
    href: "/petty-cash",
    icon: "🪙",
    desc: "管理診所日常雜項支出（打掃費、耗材、水電費等）。餘額低於警戒線時系統提示補款。",
    steps: [
      "每筆支出點「＋新增支出」，填入日期、金額、項目",
      "系統即時更新餘額",
      "餘額低於警戒線時，點「申請補款」產出報表",
      "撥款後記錄補款金額，水位恢復",
    ],
    roles: "限行政與管理員",
  },
  {
    id: "08",
    title: "月報表",
    href: "/reports",
    icon: "📈",
    desc: "整合所有模組數據，每月產出損益摘要、心理師場次統計、空間稼動率與 KPI 報表。",
    steps: [
      "進入「月報表」，選擇要查看的年月",
      "系統自動彙整當月諮商總收入、心理師酬勞、零用金支出",
      "查看診所應得毛利（30%）與淨收益估算",
      "確認墊付金額（機構應收未收 × 70%）",
    ],
    roles: "限行政與管理員",
  },
];

const roles = [
  {
    title: "心理師",
    color: "bg-blue-50 border-blue-200",
    headerColor: "bg-blue-100 text-blue-800",
    can: [
      "建立／取消當日及未來的預約",
      "查看個人門診名單與流水帳",
      "查看個人當月應得酬勞",
    ],
    cannot: [
      "修改已發生（前一日以前）的任何紀錄",
      "查看其他心理師的個案或帳務",
      "存取財務核銷、月報表等管理功能",
    ],
  },
  {
    title: "行政 / 會計",
    color: "bg-amber-50 border-amber-200",
    headerColor: "bg-amber-100 text-amber-800",
    can: [
      "所有個案資料的新增與管理",
      "處理排診、提醒電訪紀錄",
      "收費登載、收款狀態更新",
      "機構請款操作、心理師酬勞月結",
      "零用金記帳與補款申請",
      "查看與匯出月報表",
    ],
    cannot: ["修改已發生的預約或帳務（限管理員）"],
  },
  {
    title: "管理員",
    color: "bg-green-50 border-green-200",
    headerColor: "bg-green-100 text-green-800",
    can: [
      "以上全部功能",
      "修改已發生日期的帳務（需填寫原因，留存修改紀錄）",
      "管理機構、帳號設定",
      "查看完整稽核紀錄",
    ],
    cannot: [],
  },
];

export default function GuidePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-10 pb-16">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">使用簡介</h1>
        <p className="mt-2 text-gray-500">
          CheerPsy 心理診療所管理系統共分為 8 個功能模組，涵蓋個案管理、預約排程、財務核銷到月報表。
        </p>
      </div>

      {/* Core flow */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-800">系統核心流程</h2>
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-5">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {[
              { label: "建立個案", sub: "個案管理" },
              { label: "建立預約", sub: "預約管理" },
              { label: "隔日自動結算", sub: "系統執行" },
              { label: "寫入流水帳", sub: "諮商流水帳" },
              { label: "收款 / 請款", sub: "財務核銷" },
              { label: "月結報表", sub: "月報表" },
            ].map((step, i, arr) => (
              <div key={i} className="flex items-center gap-2">
                <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-center shadow-sm">
                  <div className="font-medium text-gray-800">{step.label}</div>
                  <div className="text-xs text-gray-400">{step.sub}</div>
                </div>
                {i < arr.length - 1 && <span className="text-gray-400">→</span>}
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-gray-500">
            心理師只需「建立預約」與「當日取消」兩個動作；其餘結算、帳務分流、報表產出全由系統與行政處理。
          </p>
        </div>
      </section>

      {/* Role permissions */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-800">角色權限</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {roles.map((role) => (
            <div key={role.title} className={`rounded-xl border ${role.color} overflow-hidden`}>
              <div className={`px-4 py-2.5 font-semibold ${role.headerColor}`}>{role.title}</div>
              <div className="space-y-3 p-4">
                <div>
                  <p className="mb-1.5 text-xs font-medium text-gray-500 uppercase tracking-wide">可操作</p>
                  <ul className="space-y-1">
                    {role.can.map((item, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-sm text-gray-700">
                        <span className="mt-0.5 text-green-500">✓</span>
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
                {role.cannot.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs font-medium text-gray-500 uppercase tracking-wide">不可操作</p>
                    <ul className="space-y-1">
                      {role.cannot.map((item, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-sm text-gray-700">
                          <span className="mt-0.5 text-red-400">✕</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Modules */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-800">功能模組說明</h2>
        <div className="space-y-4">
          {modules.map((mod) => (
            <div key={mod.id} className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="flex items-center gap-3 border-b border-gray-100 bg-gray-50 px-5 py-3">
                <span className="text-xl">{mod.icon}</span>
                <div>
                  <span className="text-xs font-medium text-gray-400">模組 {mod.id}　</span>
                  <span className="font-semibold text-gray-800">{mod.title}</span>
                </div>
                <span className="ml-auto rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-500">
                  {mod.roles}
                </span>
              </div>
              <div className="grid gap-4 p-5 md:grid-cols-2">
                <div>
                  <p className="text-sm text-gray-600">{mod.desc}</p>
                </div>
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">操作步驟</p>
                  <ol className="space-y-1">
                    {mod.steps.map((step, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
                          {i + 1}
                        </span>
                        {step}
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Key rules */}
      <section>
        <h2 className="mb-4 text-lg font-semibold text-gray-800">重要規則</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {[
            {
              icon: "⏰",
              title: "當日取消原則",
              desc: "個案未到請於當日取消預約。隔日結算後視為「已執行」，帳務自動產生，逾時不得修改（限管理員介入）。",
            },
            {
              icon: "🔒",
              title: "帳務鎖定原則",
              desc: "已發生日期的帳務由系統鎖定，基層人員無法竄改。管理員修改需填寫原因，全程留存稽核紀錄。",
            },
            {
              icon: "💹",
              title: "70 / 30 抽成",
              desc: "每筆諮商費用固定拆分：心理師 70%（月結支付），診所 30%（場地與行政費用）。系統自動計算，無需手動填寫。",
            },
            {
              icon: "🏦",
              title: "機構墊付注意",
              desc: "機構個案諮商完成後先付心理師酬勞，機構撥款可能延遲數週。月報表會顯示「診所目前墊付金額」供管理層掌握資金壓力。",
            },
          ].map((rule) => (
            <div key={rule.title} className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xl">{rule.icon}</span>
                <span className="font-semibold text-gray-800">{rule.title}</span>
              </div>
              <p className="text-sm text-gray-600">{rule.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
