"use client";

import { useEffect } from "react";

export interface HelpStep {
  text: string;
  sub?: string;
}

export interface HelpSection {
  heading: string;
  type: "steps" | "tips" | "notes" | "text";
  items: (string | HelpStep)[];
}

export interface HelpContent {
  title: string;
  overview: string;
  sections: HelpSection[];
}

interface Props {
  open: boolean;
  onClose: () => void;
  content: HelpContent;
}

export default function HelpDrawer({ open, onClose, content }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    if (open) document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      {/* backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
      />
      {/* drawer */}
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col bg-white shadow-2xl">
        {/* header */}
        <div className="flex items-center justify-between border-b border-gray-200 bg-primary-50 px-5 py-4">
          <div>
            <p className="text-xs font-medium text-primary-600 uppercase tracking-wide">操作說明</p>
            <h2 className="text-base font-bold text-gray-900">{content.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* overview */}
          <p className="text-sm text-gray-600 leading-relaxed">{content.overview}</p>

          {content.sections.map((section, si) => (
            <div key={si}>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                {section.type === "steps" && <span className="text-primary-500">▶</span>}
                {section.type === "tips" && <span className="text-amber-500">⚠</span>}
                {section.type === "notes" && <span className="text-blue-500">💡</span>}
                {section.type === "text" && <span className="text-gray-400">•</span>}
                {section.heading}
              </h3>

              {section.type === "steps" && (
                <ol className="space-y-2">
                  {section.items.map((item, ii) => {
                    const text = typeof item === "string" ? item : item.text;
                    const sub = typeof item === "string" ? undefined : item.sub;
                    return (
                      <li key={ii} className="flex items-start gap-2.5">
                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
                          {ii + 1}
                        </span>
                        <div>
                          <p className="text-sm text-gray-700">{text}</p>
                          {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}

              {section.type === "tips" && (
                <ul className="space-y-1.5">
                  {section.items.map((item, ii) => (
                    <li key={ii} className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      <span className="mt-0.5 shrink-0 text-amber-500">!</span>
                      {typeof item === "string" ? item : item.text}
                    </li>
                  ))}
                </ul>
              )}

              {section.type === "notes" && (
                <ul className="space-y-1.5">
                  {section.items.map((item, ii) => (
                    <li key={ii} className="flex items-start gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
                      <span className="mt-0.5 shrink-0">💡</span>
                      {typeof item === "string" ? item : item.text}
                    </li>
                  ))}
                </ul>
              )}

              {section.type === "text" && (
                <ul className="space-y-1">
                  {section.items.map((item, ii) => (
                    <li key={ii} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-300" />
                      {typeof item === "string" ? item : item.text}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>

        {/* footer */}
        <div className="border-t border-gray-100 px-5 py-3">
          <p className="text-xs text-gray-400">管理員版說明　CheerPsy v2</p>
        </div>
      </div>
    </>
  );
}
