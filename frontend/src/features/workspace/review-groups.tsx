"use client";
import { useEffect, useRef, useState } from "react";

type GroupEntry = {
  entry_id: string;
  kind: string;
  primary_entry_id?: string | null;
  question: string;
};
export function ReviewGroups({
  entries,
  selected,
  onChange,
}: {
  entries: GroupEntry[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const primary = entries.filter((e) => e.kind === "primary");
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  const names = primary.flatMap((e, i) => (selected.includes(e.entry_id) ? [`问题${i + 1}`] : []));
  return (
    <div
      ref={box}
      className="w-full min-w-0 max-w-[36rem] rounded-control border border-line"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          setOpen(false);
          box.current?.querySelector("button")?.focus();
        }
      }}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls="review-group-options"
        className="flex w-full items-center gap-3 rounded-control px-3 py-2 text-left text-base font-normal"
        onClick={() => setOpen(!open)}
      >
        <span className="min-w-0 flex-1">
          {names.length ? `已选 ${names.length} 组 · ${names.join("、")}` : "选择题组"}
        </span>
        <span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <fieldset id="review-group-options" className="space-y-3 border-t border-line p-3">
          <legend className="sr-only">指定题组</legend>
          {primary.map((entry, index) => {
            const follow = entries.filter(
              (e) => e.kind === "follow_up" && e.primary_entry_id === entry.entry_id,
            );
            return (
              <div key={entry.entry_id} className="min-w-0 space-y-1">
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-2 shrink-0"
                    checked={selected.includes(entry.entry_id)}
                    aria-label={`问题 ${index + 1} · ${entry.question}`}
                    onChange={(event) =>
                      onChange(
                        primary
                          .filter((e) =>
                            e.entry_id === entry.entry_id
                              ? event.target.checked
                              : selected.includes(e.entry_id),
                          )
                          .map((e) => e.entry_id),
                      )
                    }
                  />
                  <span className="min-w-0">
                    <span className="font-medium">问题 {index + 1}</span>
                    {follow.length > 0 && (
                      <span className="ml-2 text-sm text-secondary">含 {follow.length} 个追问</span>
                    )}
                    <span className="line-clamp-2">{entry.question}</span>
                  </span>
                </label>
                <details className="ml-6 text-sm text-secondary">
                  <summary className="cursor-pointer">查看完整题组</summary>
                  <div className="mt-2 space-y-2 text-base text-ink">
                    <p>
                      问题 {index + 1}：{entry.question}
                    </p>
                    {follow.map((e, n) => (
                      <p key={e.entry_id} className="ml-4">
                        问题 {index + 1}.{n + 1}：{e.question}
                      </p>
                    ))}
                  </div>
                </details>
              </div>
            );
          })}
        </fieldset>
      )}
    </div>
  );
}
