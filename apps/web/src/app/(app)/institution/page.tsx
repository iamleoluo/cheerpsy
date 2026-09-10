"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useApi, useApiMutation } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  Field,
  FilterBar,
  Input,
  Modal,
  QuotaMeter,
  Select,
  StatBar,
  type Column,
} from "@/components/ui";

/**
 * 機構合約清單（09 §3.7）。一頁的單位是**合約**，方案包在裡面。
 *
 * 改寫的理由是你的回饋：「不同機構的部分，每個機構都要點點點」。
 *
 * 舊版每列只有「合約名 ＋ 面板標記 ＋ 查看 →」，而 09 §3.7 規定每列要顯示
 * **機構 · 合約名 · 期間 · 使用中個案數 · 額度概況 · 專屬／通用面板標記**——
 * 少的正是「使用中個案數」與「額度概況」這兩個真正有資訊量的，所以行政只能
 * 一份一份點進去才知道裡面什麼狀況。
 *
 * 現在一張表看完 11 份合約：誰快用完額度、誰還沒有個案、哪幾份有專屬面板。
 * 那兩個數字由後端一次聚合算好（11 §4.1 的通則：跨表判斷不放前端）。
 */

interface ContractRow {
  id: number;
  institution_id: number;
  institution_name: string | null;
  name: string;
  contact_name: string | null;
  contact_phone: string | null;
  valid_from: string | null;
  valid_until: string | null;
  is_active: boolean;
  has_dedicated_module: boolean;
  plan_count: number;
  active_case_count: number;
  quota_used: number | null;
  quota_limit: number | null;
  quota_unit: string | null;
  quota_scope: string | null;
}

/** 額度用到幾成才算「該注意了」。90% 以上是 09 §3.3 國軍面板的「快見底預警」。 */
const NEARLY_FULL = 0.9;

export default function InstitutionContractListPage() {
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [q, setQ] = useState("");
  const [scope, setScope] = useState<"active" | "all">("active");

  const { data, error, loading, refetch } = useApi<ContractRow[]>(
    "/institution/contracts?include_inactive=true",
  );

  const { rows, stats } = useMemo(() => {
    const all = data ?? [];
    const kw = q.trim().toLowerCase();
    const rows = all
      .filter((c) => (scope === "all" ? true : c.is_active))
      .filter(
        (c) =>
          !kw ||
          c.name.toLowerCase().includes(kw) ||
          (c.institution_name ?? "").toLowerCase().includes(kw),
      );
    const active = all.filter((c) => c.is_active);
    return {
      rows,
      stats: {
        contracts: active.length,
        dedicated: active.filter((c) => c.has_dedicated_module).length,
        cases: active.reduce((s, c) => s + c.active_case_count, 0),
        nearlyFull: active.filter(
          (c) => c.quota_limit && c.quota_used != null && c.quota_used / c.quota_limit >= NEARLY_FULL,
        ).length,
      },
    };
  }, [data, q, scope]);

  const columns: readonly Column<ContractRow>[] = [
    {
      key: "name",
      header: "合約",
      cell: (c) => (
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-ink">{c.name}</span>
            {c.has_dedicated_module ? (
              <Badge tone="active" size="mini">專屬</Badge>
            ) : (
              <Badge tone="muted" size="mini">通用</Badge>
            )}
            {!c.is_active && <Badge tone="muted" size="mini">已停用</Badge>}
          </div>
          <div className="truncate text-[10.5px] text-ink-3">{c.institution_name ?? "（未分類）"}</div>
        </div>
      ),
    },
    {
      key: "plans",
      header: "方案",
      align: "right",
      nowrap: true,
      width: "w-16",
      cell: (c) => <span className="text-ink-2">{c.plan_count}</span>,
    },
    {
      key: "cases",
      header: "使用中個案",
      align: "right",
      nowrap: true,
      width: "w-24",
      cell: (c) =>
        c.active_case_count > 0 ? (
          <span className="font-semibold text-ink">{c.active_case_count}</span>
        ) : (
          // 有合約卻沒個案，多半是還沒開始跑或已經跑完——值得一眼看出來
          <span className="text-st-muted">—</span>
        ),
    },
    {
      key: "quota",
      header: "額度概況",
      width: "w-40",
      cell: (c) =>
        c.quota_limit && c.quota_used != null ? (
          <QuotaMeter used={c.quota_used} limit={c.quota_limit} unit={c.quota_unit ?? "count"} />
        ) : (
          <span className="text-[10.5px] text-st-muted">不設上限</span>
        ),
    },
    {
      key: "period",
      header: "期間",
      nowrap: true,
      width: "w-40",
      cell: (c) =>
        c.valid_from || c.valid_until ? (
          <span className="ident text-[10.5px] text-ink-3">
            {c.valid_from ?? "—"} ~ {c.valid_until ?? "—"}
          </span>
        ) : (
          <span className="text-st-muted">—</span>
        ),
    },
    {
      key: "contact",
      header: "承辦",
      cell: (c) =>
        c.contact_name ? (
          <span className="text-[10.5px] text-ink-2">
            {c.contact_name}
            {c.contact_phone && <span className="ml-1 text-ink-3">{c.contact_phone}</span>}
          </span>
        ) : (
          <span className="text-st-muted">—</span>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold text-ink">機構合約</h1>
        <span className="text-xs text-ink-3">
          一份合約 ＝ 與某機構的一段合作；方案、額度、費率、核銷都在合約專頁裡管理
        </span>
        <div className="ml-auto">
          <Button variant="accent" size="sm" onClick={() => setShowCreate(true)}>
            ＋ 新增合約
          </Button>
        </div>
      </div>

      <AsyncBoundary
        loading={loading}
        error={error}
        data={data}
        onRetry={refetch}
        skeleton={<div className="h-[4.5rem] animate-pulse rounded-card bg-surface-2" />}
      >
        {() => (
          <StatBar
            stats={[
              { label: "生效中合約", value: stats.contracts },
              { label: "專屬面板", value: stats.dedicated, sub: `其餘 ${stats.contracts - stats.dedicated} 份走通用版` },
              { label: "使用中個案", value: stats.cases },
              {
                label: "額度將滿",
                value: stats.nearlyFull,
                tone: stats.nearlyFull > 0 ? "warn" : "default",
                sub: "已用逾九成",
              },
            ]}
          />
        )}
      </AsyncBoundary>

      <FilterBar>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋機構或合約名稱"
          className="max-w-xs"
        />
        <Select value={scope} onChange={(e) => setScope(e.target.value as "active" | "all")} className="w-32">
          <option value="active">僅生效中</option>
          <option value="all">含已停用</option>
        </Select>
        <span className="text-[10.5px] text-ink-3">{rows.length} 份</span>
      </FilterBar>

      <Card>
        <div className="p-3">
          <AsyncBoundary
            loading={loading}
            error={error}
            data={rows}
            onRetry={refetch}
            empty={
              <EmptyState
                title={q ? "沒有符合的合約" : "尚無機構合約"}
                hint={
                  q
                    ? "換個關鍵字，或切換成「含已停用」。"
                    : "一份合約代表與某機構的一段合作。建立之後，方案、費率規則與核銷路由都在合約專頁裡設定。"
                }
                action={!q ? <Button size="sm" onClick={() => setShowCreate(true)}>＋ 新增合約</Button> : undefined}
              />
            }
          >
            {(list) => (
              <DataTable
                columns={columns}
                rows={list}
                rowKey={(c) => c.id}
                minWidth="56rem"
                onRowClick={(c) => router.push(`/institution/${c.id}`)}
                rowClassName={(c) => (!c.is_active ? "opacity-60" : undefined)}
              />
            )}
          </AsyncBoundary>
        </div>
      </Card>

      {showCreate && (
        <CreateContractModal
          onClose={() => setShowCreate(false)}
          onCreated={(id) => router.push(`/institution/${id}`)}
        />
      )}
    </div>
  );
}

function CreateContractModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const { data: institutions } = useApi<{ id: number; name: string }[]>("/institutions");
  const { mutate, pending } = useApiMutation();
  const [form, setForm] = useState({
    institutionId: "",
    newInstitutionName: "",
    name: "",
    contactName: "",
    contactPhone: "",
    eligibilityNote: "",
    validFrom: "",
    validUntil: "",
  });
  const [error, setError] = useState("");
  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      let instId = form.institutionId;
      if (!instId && form.newInstitutionName.trim()) {
        const inst = await mutate<{ id: number }>("/institutions", {
          method: "POST",
          body: JSON.stringify({ name: form.newInstitutionName.trim() }),
        });
        instId = String(inst.id);
      }
      if (!instId) throw new Error("請選擇機構單位，或填寫新機構名稱");

      const contract = await mutate<{ id: number }>("/institution/contracts", {
        method: "POST",
        body: JSON.stringify({
          institution_id: Number(instId),
          name: form.name,
          contact_name: form.contactName || null,
          contact_phone: form.contactPhone || null,
          eligibility_note: form.eligibilityNote || null,
          valid_from: form.validFrom || null,
          valid_until: form.validUntil || null,
        }),
      });
      onCreated(contract.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal
      open
      onOpenChange={(o) => !o && onClose()}
      title="新增機構合約"
      hint="建立之後，方案、費率規則與核銷路由在合約專頁裡設定"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>取消</Button>
          <Button variant="accent" size="sm" loading={pending} onClick={handleSubmit}>建立</Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {error && (
          <p className="rounded-control bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</p>
        )}

        <Field label="機構單位" hint={!form.institutionId ? "選「新增機構」時，請在下方填名稱" : undefined}>
          {(p) => (
            <Select {...p} value={form.institutionId} onChange={(e) => set("institutionId", e.target.value)}>
              <option value="">— 新增機構 —</option>
              {(institutions ?? []).map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </Select>
          )}
        </Field>

        {!form.institutionId && (
          <Field label="新機構名稱">
            {(p) => (
              <Input {...p} value={form.newInstitutionName}
                onChange={(e) => set("newInstitutionName", e.target.value)}
                placeholder="如「臺南市政府衛生局」" />
            )}
          </Field>
        )}

        <Field label="合約名稱" required>
          {(p) => (
            <Input {...p} required value={form.name} onChange={(e) => set("name", e.target.value)}
              placeholder="如「衛生局心理健康服務合約」" />
          )}
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="承辦人">
            {(p) => <Input {...p} value={form.contactName} onChange={(e) => set("contactName", e.target.value)} />}
          </Field>
          <Field label="聯絡電話">
            {(p) => <Input {...p} value={form.contactPhone} onChange={(e) => set("contactPhone", e.target.value)} />}
          </Field>
        </div>

        <Field label="方案身份條件" hint="誰符合資格用這份合約，如「15-45 歲民眾」">
          {(p) => (
            <Input {...p} value={form.eligibilityNote}
              onChange={(e) => set("eligibilityNote", e.target.value)} />
          )}
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="生效日">
            {(p) => <Input {...p} type="date" value={form.validFrom} onChange={(e) => set("validFrom", e.target.value)} />}
          </Field>
          <Field label="到期日">
            {(p) => <Input {...p} type="date" value={form.validUntil} onChange={(e) => set("validUntil", e.target.value)} />}
          </Field>
        </div>
      </form>
    </Modal>
  );
}
