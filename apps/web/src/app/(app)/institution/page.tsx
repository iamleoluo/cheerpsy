"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { clientFetch } from "@/lib/client-api";

/**
 * 機構合約清單（09 §3.7）：所有合約，依機構分組，點入每份合約各自的
 * 專頁（四分頁骨架，見 [id]/page.tsx）。一頁的單位是「合約」，方案包在
 * 裡面——這是 09 §3 已定案的分層架構。
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
}
interface InstitutionOption {
  id: number;
  name: string;
}

export default function InstitutionContractListPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const router = useRouter();
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const fetchContracts = () => {
    if (!token) return;
    setLoading(true);
    clientFetch("/institution/contracts?include_inactive=true", token)
      .then(setContracts)
      .catch(() => setContracts([]))
      .finally(() => setLoading(false));
  };

  useEffect(fetchContracts, [token]);

  const byInstitution = contracts.reduce<Record<string, ContractRow[]>>((acc, c) => {
    const key = c.institution_name ?? "（未分類）";
    (acc[key] ??= []).push(c);
    return acc;
  }, {});

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <h1 className="text-2xl font-bold">機構合約</h1>
        <button onClick={() => setShowCreate(true)} className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700">
          ＋ 新增機構合約
        </button>
      </div>
      <p className="mb-6 text-sm text-gray-400">一份合約 = 與某機構的一段合作，底下的方案（含額度、費率、核銷路由）都在合約專頁裡管理</p>

      {loading && <p className="text-sm text-gray-400">載入中...</p>}
      {!loading && contracts.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">尚無合約資料</div>
      )}

      <div className="space-y-6">
        {Object.entries(byInstitution).map(([institutionName, rows]) => (
          <div key={institutionName}>
            <h2 className="mb-2 text-sm font-semibold text-gray-500">{institutionName}</h2>
            <div className="overflow-hidden rounded-lg border border-gray-200">
              {rows.map((c) => (
                <Link
                  key={c.id}
                  href={`/institution/${c.id}`}
                  className="flex items-center justify-between border-b border-gray-100 bg-white px-4 py-3 text-sm last:border-b-0 hover:bg-gray-50"
                >
                  <div>
                    <span className="font-medium">{c.name}</span>
                    {!c.is_active && <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-400">已停用</span>}
                    {c.contact_name && <span className="ml-2 text-xs text-gray-400">承辦 {c.contact_name}{c.contact_phone ? ` · ${c.contact_phone}` : ""}</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    {c.valid_from && c.valid_until && <span>{c.valid_from} ~ {c.valid_until}</span>}
                    <span className="text-primary-500">查看 →</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      {showCreate && (
        <CreateContractModal
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={(id) => router.push(`/institution/${id}`)}
        />
      )}
    </div>
  );
}

function CreateContractModal({
  token, onClose, onCreated,
}: { token: string; onClose: () => void; onCreated: (id: number) => void }) {
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [institutionId, setInstitutionId] = useState("");
  const [newInstitutionName, setNewInstitutionName] = useState("");
  const [name, setName] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [eligibilityNote, setEligibilityNote] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    clientFetch("/institutions", token).then(setInstitutions).catch(() => {});
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      let instId = institutionId;
      if (!instId && newInstitutionName.trim()) {
        const inst = await clientFetch("/institutions", token, {
          method: "POST",
          body: JSON.stringify({ name: newInstitutionName.trim() }),
        });
        instId = String(inst.id);
      }
      if (!instId) throw new Error("請選擇機構單位或填寫新機構名稱");

      const contract = await clientFetch("/institution/contracts", token, {
        method: "POST",
        body: JSON.stringify({
          institution_id: Number(instId),
          name,
          contact_name: contactName || null,
          contact_phone: contactPhone || null,
          eligibility_note: eligibilityNote || null,
          valid_from: validFrom || null,
          valid_until: validUntil || null,
        }),
      });
      onCreated(contract.id);
    } catch (e: any) {
      setError(e.message ?? "建立失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="w-[420px] rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 font-semibold">新增機構合約</h3>
        {error && <div className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">機構單位</span>
            <select value={institutionId} onChange={(e) => setInstitutionId(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="">— 新增機構 —</option>
              {institutions.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
            {!institutionId && (
              <input
                value={newInstitutionName}
                onChange={(e) => setNewInstitutionName(e.target.value)}
                placeholder="新機構名稱"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            )}
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">合約名稱 <span className="text-rose-500">*</span></span>
            <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="如「衛生局心理健康服務合約」" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">承辦人</span>
              <input value={contactName} onChange={(e) => setContactName(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">聯絡電話</span>
              <input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">方案身份條件</span>
            <input value={eligibilityNote} onChange={(e) => setEligibilityNote(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="如「15-45 歲民眾」" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">生效日</span>
              <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">到期日</span>
              <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="flex-1 rounded-lg bg-primary-600 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              {saving ? "建立中…" : "建立"}
            </button>
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-500 hover:bg-gray-50">取消</button>
          </div>
        </form>
      </div>
    </div>
  );
}
