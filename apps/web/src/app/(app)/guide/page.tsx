"use client";

import { useState } from "react";
import { guideModules, type DocSection, type DocModule } from "@/lib/guide-content";

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
      if (hash && guideModules.find((m) => m.id === hash)) return hash;
    }
    return "overview";
  });
  const active = guideModules.find((m) => m.id === activeId) ?? guideModules[0];

  return (
    <div className="flex h-[calc(100vh-64px)] overflow-hidden">
      {/* sidebar */}
      <nav className="hidden w-52 shrink-0 overflow-y-auto border-r border-gray-200 bg-gray-50 md:block">
        <div className="px-4 py-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">功能模組</p>
          <ul className="space-y-0.5">
            {guideModules.map((m) => (
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
              {guideModules.map((m) => (
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
            {guideModules.findIndex((m) => m.id === activeId) > 0 ? (
              <button
                onClick={() => setActiveId(guideModules[guideModules.findIndex((m) => m.id === activeId) - 1].id)}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
              >
                ← {guideModules[guideModules.findIndex((m) => m.id === activeId) - 1].title}
              </button>
            ) : <div />}
            {guideModules.findIndex((m) => m.id === activeId) < guideModules.length - 1 ? (
              <button
                onClick={() => setActiveId(guideModules[guideModules.findIndex((m) => m.id === activeId) + 1].id)}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
              >
                {guideModules[guideModules.findIndex((m) => m.id === activeId) + 1].title} →
              </button>
            ) : <div />}
          </div>
        </div>
      </main>
    </div>
  );
}
