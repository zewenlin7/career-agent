"use client";
import { useEffect, useState } from "react";
import type { ResumeSection } from "../onboarding/contracts";
import { sectionLabels } from "../onboarding/contracts";
import type { Presentation } from "./contracts";
export const defaultPresentation: Presentation = {
  hidden_sections: [],
  hidden_item_ids: [],
  compact_item_ids: [],
  item_order: [],
  experience_order: "work_first",
};
export function ResumeView({
  sections,
  presentation: input,
}: {
  sections: ResumeSection[];
  presentation?: Presentation;
  onPresentation: (p: Presentation) => void;
  disabled?: boolean;
}) {
  const presentation = { ...defaultPresentation, ...input };
  const order =
    presentation.experience_order === "projects_first"
      ? ["summary", "education", "projects", "experience", "skills"]
      : ["summary", "education", "experience", "projects", "skills"];
  return (
    <div className="divide-y divide-line">
      {[...sections]
        .sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name))
        .map((section) => {
          const hidden = presentation.hidden_sections.includes(section.name);
          const items = [...section.items]
            .sort((a, b) => {
              const rank = (id: string, fallback: number) =>
                presentation.item_order?.includes(id)
                  ? presentation.item_order.indexOf(id)
                  : 500 + fallback;
              return (
                rank(a.item_id, a.ordering) - rank(b.item_id, b.ordering) ||
                a.item_id.localeCompare(b.item_id)
              );
            })
            .filter((i) => !presentation.hidden_item_ids?.includes(i.item_id));
          if (hidden || !items.length) return null;
          return (
            <section key={section.section_id} className="py-5">
              <header className="mb-3 flex items-center justify-between gap-3">
                <h3 className="font-serif text-xl">{sectionLabels[section.name]}</h3>
              </header>
              {!hidden &&
                items.map((item) => (
                  <Entry
                    key={item.item_id}
                    text={
                      presentation.compact_item_ids?.includes(item.item_id)
                        ? item.short_text || item.text
                        : item.text
                    }
                    layout={(item as unknown as { layout?: Layout }).layout}
                  />
                ))}
            </section>
          );
        })}
    </div>
  );
}
type Layout = {
  text_sha256: string;
  title_line: number;
  date_lines: number[];
  subtitle_lines: number[];
};
function Entry({ text, layout }: { text: string; layout?: Layout }) {
  const [hash, setHash] = useState("");
  useEffect(() => {
    let active = true;
    void crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then((value) => {
      if (active)
        setHash([...new Uint8Array(value)].map((n) => n.toString(16).padStart(2, "0")).join(""));
    });
    return () => {
      active = false;
    };
  }, [text]);
  const lines = text.split("\n");
  const indices = layout ? [layout.title_line, ...layout.date_lines, ...layout.subtitle_lines] : [];
  if (!layout || hash !== layout.text_sha256 || indices.some((n) => n < 0 || n >= lines.length))
    return <p className="mb-4 whitespace-pre-wrap break-words">{text}</p>;
  return (
    <article className="mb-4 space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <strong>{lines[layout.title_line]}</strong>
        <span>{layout.subtitle_lines.map((i) => lines[i]).join(" · ")}</span>
        <span className="ml-auto whitespace-nowrap text-sm text-secondary">
          {layout.date_lines.map((i) => lines[i]).join(" – ")}
        </span>
      </div>
      <ul className="list-disc space-y-1 pl-5">
        {lines.map((line, i) => !indices.includes(i) && line.trim() && <li key={i}>{line}</li>)}
      </ul>
    </article>
  );
}
