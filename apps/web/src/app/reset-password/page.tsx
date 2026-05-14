"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<"key" | "form">("key");
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const verifyKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auth/invite/${key.trim()}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Invalid key");
      }
      const data = await res.json();
      if (data.type !== "reset") {
        throw new Error("This key is for registration, not password reset");
      }
      setName(data.name);
      setStep("form");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== password2) {
      setError("Password confirmation does not match");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invite_key: key.trim(), password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Reset failed");
      }
      alert("Password updated! Redirecting to login...");
      router.push("/login");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-lg">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-primary-700">CheerPsy</h1>
          <p className="mt-1 text-sm text-gray-500">重設密碼</p>
        </div>

        {step === "key" && (
          <form onSubmit={verifyKey} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">重設金鑰</label>
              <input
                type="text"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                required
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono tracking-wider focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                placeholder="CHEER-XXXX-XXXX-XXXX"
              />
              <p className="mt-1 text-xs text-gray-400">請輸入管理員提供的密碼重設金鑰</p>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button type="submit" disabled={loading} className="w-full rounded-lg bg-primary-600 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              {loading ? "驗證中..." : "驗證金鑰"}
            </button>
          </form>
        )}

        {step === "form" && (
          <form onSubmit={handleReset} className="space-y-4">
            <div className="rounded-lg bg-primary-50 p-3 text-sm">
              <p className="font-medium text-primary-700">{name}</p>
              <p className="text-xs text-primary-500">重設密碼</p>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">新密碼</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">確認新密碼</label>
              <input
                type="password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                required
                minLength={6}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button type="submit" disabled={loading} className="w-full rounded-lg bg-primary-600 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              {loading ? "更新中..." : "更新密碼"}
            </button>
          </form>
        )}

        <div className="mt-4 text-center">
          <a href="/login" className="text-xs text-gray-400 hover:text-primary-600">返回登入</a>
        </div>
      </div>
    </div>
  );
}
