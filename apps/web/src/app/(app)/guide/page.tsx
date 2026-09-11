"use client";

import { useState } from "react";
import { guideModules, type DocSection, type DocModule } from "@/lib/guide-content";

/* ───── helpers ───── */
function SectionBlock({ section }: { section: DocSection }) {
  if (section.type === "flow") {
    return (
      <div className="mb-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">{section.heading}</h4>
        <div className="flex flex-wrap items-center gap-2">
          {section.items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-sm text-ink-2 shadow-sm">
                {item}
              </div>
              {i < section.items.length - 1 && <span className="text-st-muted">→</span>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (section.type === "steps") {
    return (
      <div className="mb-5">
        <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-ink-3">
          <span className="mr-1 text-accent">▶</span>{section.heading}
        </h4>
        <ol className="space-y-2">
          {section.items.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
                {i + 1}
              </span>
              <span className="text-sm text-ink-2">{item}</span>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  if (section.type === "tips") {
    return (
      <div className="mb-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
          <span className="mr-1 text-st-warn">⚠</span>{section.heading}
        </h4>
        <ul className="space-y-2">
          {section.items.map((item, i) => (
            <li key={i} className="rounded-lg bg-st-warn-bg border border-st-warn/30 px-3 py-2 text-sm text-st-warn">
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
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
          <span className="mr-1">💡</span>{section.heading}
        </h4>
        <ul className="space-y-2">
          {section.items.map((item, i) => (
            <li key={i} className="rounded-lg bg-accent-soft text-accent border border-accent/25 px-3 py-2 text-sm">
              {item}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="mb-5">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">{section.heading}</h4>
      <ul className="space-y-1.5">
        {section.items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-ink-2">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-line-2" />
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
      <nav className="hidden w-52 shrink-0 overflow-y-auto border-r border-line bg-surface-2 md:block">
        <div className="px-4 py-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-3">功能模組</p>
          <ul className="space-y-0.5">
            {guideModules.map((m) => (
              <li key={m.id}>
                <button
                  onClick={() => setActiveId(m.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                    activeId === m.id
                      ? "bg-accent-soft font-semibold text-accent"
                      : "text-ink-2 hover:bg-surface-3 hover:text-ink"
                  }`}
                >
                  <span className="mr-2">{m.icon}</span>
                  {m.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-line px-4 py-4">
          <p className="text-xs text-ink-3">管理員版說明</p>
          <p className="text-xs text-ink-3">CheerPsy v2</p>
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
              className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
            >
              {guideModules.map((m) => (
                <option key={m.id} value={m.id}>{m.icon} {m.title}</option>
              ))}
            </select>
          </div>

          {/* module header */}
          <div className="mb-6 border-b border-line pb-5">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{active.icon}</span>
              <div>
                <h1 className="text-xl font-bold text-ink">{active.title}</h1>
                <p className="text-sm text-ink-3">{active.tagline}</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-ink-2">{active.overview}</p>
          </div>

          {/* sections */}
          <div>
            {active.sections.map((section, i) => (
              <SectionBlock key={i} section={section} />
            ))}
          </div>

          {/* nav buttons */}
          <div className="mt-8 flex items-center justify-between border-t border-line pt-5">
            {guideModules.findIndex((m) => m.id === activeId) > 0 ? (
              <button
                onClick={() => setActiveId(guideModules[guideModules.findIndex((m) => m.id === activeId) - 1].id)}
                className="flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink"
              >
                ← {guideModules[guideModules.findIndex((m) => m.id === activeId) - 1].title}
              </button>
            ) : <div />}
            {guideModules.findIndex((m) => m.id === activeId) < guideModules.length - 1 ? (
              <button
                onClick={() => setActiveId(guideModules[guideModules.findIndex((m) => m.id === activeId) + 1].id)}
                className="flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink"
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
