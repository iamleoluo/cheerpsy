"use client";

import { useEffect } from "react";
import { guideModules, type DocSection } from "@/lib/guide-content";

// Legacy type kept for backward compat (pages still pass content= for now)
export interface HelpStep { text: string; sub?: string; }
export interface HelpSection { heading: string; type: "steps" | "tips" | "notes" | "text"; items: (string | HelpStep)[]; }
export interface HelpContent { title: string; overview: string; sections: HelpSection[]; guideId?: string; }

interface Props {
  open: boolean;
  onClose: () => void;
  /** Pass either guideId (renders from shared guide-content) or legacy content= */
  guideId?: string;
  content?: HelpContent;
}

function SectionBlock({ section }: { section: DocSection | HelpSection }) {
  const type = section.type as string;
  const items = section.items as string[];

  return (
    <div>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">
        {type === "steps" && <span className="text-accent">▶</span>}
        {type === "tips" && <span className="text-st-warn">⚠</span>}
        {type === "notes" && <span className="text-accent">💡</span>}
        {(type === "text" || type === "flow") && <span className="text-ink-3">•</span>}
        {section.heading}
      </h3>

      {type === "steps" && (
        <ol className="space-y-2">
          {items.map((item, ii) => {
            const text = typeof item === "string" ? item : (item as HelpStep).text;
            return (
              <li key={ii} className="flex items-start gap-2.5">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
                  {ii + 1}
                </span>
                <p className="text-sm text-ink-2">{text}</p>
              </li>
            );
          })}
        </ol>
      )}

      {type === "tips" && (
        <ul className="space-y-1.5">
          {items.map((item, ii) => (
            <li key={ii} className="flex items-start gap-2 rounded-lg bg-st-warn-bg px-3 py-2 text-sm text-st-warn">
              <span className="mt-0.5 shrink-0 text-st-warn">!</span>
              {typeof item === "string" ? item : (item as HelpStep).text}
            </li>
          ))}
        </ul>
      )}

      {type === "notes" && (
        <ul className="space-y-1.5">
          {items.map((item, ii) => (
            <li key={ii} className="flex items-start gap-2 rounded-lg bg-accent-soft text-accent px-3 py-2 text-sm">
              <span className="mt-0.5 shrink-0">💡</span>
              {typeof item === "string" ? item : (item as HelpStep).text}
            </li>
          ))}
        </ul>
      )}

      {(type === "text" || type === "flow") && (
        <ul className="space-y-1">
          {items.map((item, ii) => (
            <li key={ii} className="flex items-start gap-2 text-sm text-ink-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-line-2" />
              {typeof item === "string" ? item : (item as HelpStep).text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function HelpDrawer({ open, onClose, guideId, content }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    if (open) document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  // Prefer guideId → look up from shared content; fall back to legacy content prop
  const resolvedId = guideId ?? content?.guideId;
  const module = resolvedId ? guideModules.find((m) => m.id === resolvedId) : null;

  const title = module?.title ?? content?.title ?? "";
  const overview = module?.overview ?? content?.overview ?? "";
  const sections = module?.sections ?? content?.sections ?? [];

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col bg-white shadow-2xl">
        {/* header */}
        <div className="flex items-center justify-between border-b border-line bg-accent-soft px-5 py-4">
          <div>
            <p className="text-xs font-medium text-accent uppercase tracking-wide">操作說明</p>
            <h2 className="text-base font-bold text-ink">{title}</h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-3 hover:text-ink-2">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <p className="text-sm text-ink-2 leading-relaxed">{overview}</p>
          {(sections as (DocSection | HelpSection)[]).map((section, si) => (
            <SectionBlock key={si} section={section} />
          ))}
        </div>

        {/* footer */}
        <div className="border-t border-line px-5 py-3 flex items-center justify-between">
          <p className="text-xs text-ink-3">CheerPsy v2</p>
          {resolvedId && (
            <a href={`/guide#${resolvedId}`} className="text-xs text-accent hover:underline">
              完整操作指南 →
            </a>
          )}
        </div>
      </div>
    </>
  );
}
