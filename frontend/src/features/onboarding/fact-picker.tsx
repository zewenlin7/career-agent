"use client";
import type { Fact } from "./contracts";
export function FactPicker({
  facts,
  value,
  onChange,
  label = "关联事实",
}: {
  facts: Fact[];
  value: string[];
  onChange: (ids: string[]) => void;
  label?: string;
}) {
  const missing = value.filter((id) => !facts.some((f) => f.id === id));
  return (
    <fieldset className="space-y-2 rounded-control border border-line p-3">
      <legend className="px-1 text-sm">{label}</legend>
      {!facts.length && <p className="text-sm text-secondary">暂无事实，请先添加并确认经历。</p>}
      <div className="max-h-60 space-y-2 overflow-y-auto">
        {facts.map((f) => (
          <label key={f.id} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={value.includes(f.id)}
              disabled={f.status !== "verified" && !value.includes(f.id)}
              onChange={(e) =>
                onChange(e.target.checked ? [...value, f.id] : value.filter((id) => id !== f.id))
              }
            />
            <span className="min-w-0 break-words">
              {f.statement}{" "}
              <span className="text-secondary">
                ·{" "}
                {
                  (
                    {
                      proposed: "待确认",
                      verified: "已确认",
                      rejected: "不采用",
                      superseded: "已更正",
                    } as Record<string, string>
                  )[f.status]
                }
              </span>
            </span>
          </label>
        ))}
      </div>
      {missing.map((id) => (
        <label key={id} className="flex gap-2 text-sm">
          <input type="checkbox" checked onChange={() => onChange(value.filter((v) => v !== id))} />
          <span className="break-all">未能读取的历史事实（取消勾选可移除关联）</span>
        </label>
      ))}
      {facts.some((f) => value.includes(f.id) && f.status !== "verified") && (
        <p className="text-sm text-error">包含尚未确认或已更正的事实，请核对关联后再用于简历。</p>
      )}
    </fieldset>
  );
}
