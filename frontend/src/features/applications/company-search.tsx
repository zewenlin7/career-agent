"use client";
import { useState, useEffect, useRef, useId } from "react";
import { useRead } from "@/features/workspace/client";
import { Field, control, ErrorNotice } from "@/features/workspace/ui";
import type { Page } from "@/features/workspace/contracts";
export type Company = { id: string; name: string };
export function CompanySearch({
  value: search,
  onChange,
  onSelect,
  disabled = () => false,
  label = "公司",
  showEmpty = true,
  required = false,
  onComposing,
}: {
  value: string;
  onChange: (value: string) => void;
  onSelect: (company: Company) => void;
  disabled?: (company: Company) => boolean;
  label?: string;
  showEmpty?: boolean;
  required?: boolean;
  onComposing?: (value: boolean) => void;
}) {
  const [debounced, setDebounced] = useState("");
  const [composing, setComposing] = useState(false);
  const composition = useRef(false);
  const anchor = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string>();
  const [menuHeight, setMenuHeight] = useState(224);
  useEffect(() => {
    if (composing) return;
    const timer = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search, composing]);
  // Invalidate old results immediately, including while a new query is debouncing.
  const candidates = useRead<Page<Company>>(
    !composing && search.trim() && search.trim() === debounced
      ? `companies?q=${encodeURIComponent(debounced)}&limit=8`
      : null,
  );
  const visible =
    open &&
    !composing &&
    !!search.trim() &&
    !!candidates.data &&
    (showEmpty || candidates.data.items.length > 0);
  const choose = (company: Company) => {
    if (disabled(company)) return;
    onSelect(company);
    setDebounced("");
    setOpen(false);
    setActiveId(undefined);
    input.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !anchor.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside, true);
    return () => document.removeEventListener("pointerdown", outside, true);
  }, [open]);
  useEffect(() => {
    if (!visible) return;
    const measure = () => {
      const bottom = anchor.current?.getBoundingClientRect().bottom ?? 0;
      setMenuHeight(Math.max(0, Math.min(224, window.innerHeight - bottom - 8)));
    };
    const frame = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [visible]);
  useEffect(() => {
    if (visible && activeId)
      document.getElementById(`${menuId}-${activeId}`)?.scrollIntoView({ block: "nearest" });
  }, [visible, activeId, menuId]);
  return (
    <div
      ref={anchor}
      className="relative min-w-0"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <Field label={label}>
        <input
          ref={input}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={visible}
          aria-controls={visible ? menuId : undefined}
          aria-activedescendant={visible && activeId ? `${menuId}-${activeId}` : undefined}
          autoComplete="off"
          className={`${control} font-normal placeholder:text-muted`}
          placeholder="输入公司名称"
          value={search}
          required={required}
          maxLength={200}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
            setActiveId(undefined);
          }}
          onKeyDown={(event) => {
            if (composition.current || event.nativeEvent.isComposing) return;
            if (event.key === "Escape" || event.key === "Tab") {
              setOpen(false);
              setActiveId(undefined);
              return;
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setOpen(true);
              const items = candidates.data?.items.filter((c) => !disabled(c)) ?? [];
              if (!items.length) return;
              const index = items.findIndex((c) => c.id === activeId);
              const next =
                index < 0
                  ? event.key === "ArrowDown"
                    ? 0
                    : items.length - 1
                  : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
              setActiveId(items[next].id);
            } else if (event.key === "Enter" && visible) {
              event.preventDefault();
              const company = candidates.data?.items.find((c) => c.id === activeId);
              if (company) choose(company);
            }
          }}
          onCompositionStart={() => {
            composition.current = true;
            onComposing?.(true);
            setComposing(true);
          }}
          onCompositionEnd={(e) => {
            composition.current = false;
            onComposing?.(false);
            onChange(e.currentTarget.value);
            setComposing(false);
          }}
        />
      </Field>
      <ErrorNotice code={candidates.error} />
      {visible && (
        <ul
          id={menuId}
          role="listbox"
          aria-label="公司候选"
          style={{ maxHeight: menuHeight }}
          className="absolute top-full left-0 z-20 mt-1 w-full overflow-y-auto overscroll-contain rounded-control border border-line bg-paper p-1 shadow-soft"
        >
          {candidates.data!.items.map((company) => (
            <li key={company.id} role="presentation">
              <button
                id={`${menuId}-${company.id}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={activeId === company.id}
                disabled={disabled(company)}
                className={`w-full rounded px-3 py-2 text-left text-sm break-words text-ink hover:bg-surface disabled:cursor-not-allowed disabled:text-muted ${activeId === company.id ? "bg-surface" : ""}`}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(company)}
              >
                {company.name}
              </button>
            </li>
          ))}
          {!candidates.data!.items.length && (
            <li role="presentation" className="px-3 py-2 text-sm text-secondary">
              没有找到公司
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
