import { auth } from "@/lib/auth";

export default async function DashboardPage() {
  const session = await auth();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">儀表板</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="本月諮商場次" value="--" />
        <StatCard title="本月營收" value="--" />
        <StatCard title="待收款項" value="--" />
        <StatCard title="預約提醒" value="--" />
      </div>

      <div className="mt-8 rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">系統建置中</h2>
        <p className="text-sm text-gray-600">
          歡迎使用 CheerPsy v2 營運管理系統。各模組功能正在開發中，目前已完成：
        </p>
        <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-gray-600">
          <li>使用者認證與角色權限</li>
          <li>資料庫架構（個案、預約、流水帳、空間、財務、零用金、稽核）</li>
        </ul>
        <p className="mt-3 text-sm text-gray-600">
          下一步：個案管理、預約系統、空間預約表。
        </p>
      </div>
    </div>
  );
}

function StatCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}
