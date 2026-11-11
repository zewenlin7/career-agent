"use client";
import { useEffect, useRef, useState } from "react";
import { control } from "./ui";

/** Plain text remains editable; the optional calendar never supplies an implicit date. */
export function InterviewDate({
  value,
  onChange,
  id,
  error,
}: {
  id?: string;
  error?: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(
    () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const [selectedDate = "", selectedTime = ""] = value.split(" ");
  const [hour = "", minute = ""] = selectedTime.split(":");
  const year = month.getFullYear(),
    index = month.getMonth();
  const days = new Date(year, index + 1, 0).getDate();
  return (
    <div
      ref={root}
      className="relative min-w-0 flex-1"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          input.current?.focus();
        }
      }}
    >
      <input
        ref={input}
        id={id}
        aria-label="面试时间"
        aria-invalid={!!error}
        aria-describedby={error && id ? `${id}-error` : undefined}
        className={`${control} pr-12`}
        placeholder="YYYY-MM-DD HH:mm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && (
        <p
          id={id ? `${id}-error` : undefined}
          role="alert"
          className="mt-2 text-sm font-normal text-error"
        >
          {error}
        </p>
      )}
      <button
        type="button"
        aria-label="选择面试日期时间"
        aria-expanded={open}
        className="absolute top-3 right-2 text-sm text-secondary"
        onClick={() => {
          if (!open && /^\d{4}-(0[1-9]|1[0-2])-\d{2}/.test(value))
            setMonth(new Date(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1, 1));
          setOpen(!open);
        }}
      >
        <svg
          aria-hidden="true"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M16 3v4M8 3v4M3 11h18" />
        </svg>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="面试日期选择"
          className="absolute top-full left-0 z-30 mt-1 w-64 rounded-control border border-line bg-white p-3 shadow-sm"
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              aria-label="上个月"
              onClick={() => setMonth(new Date(year, index - 1, 1))}
            >
              ‹
            </button>
            <span className="text-sm">
              {year}年{index + 1}月
            </span>
            <button
              type="button"
              aria-label="下个月"
              onClick={() => setMonth(new Date(year, index + 1, 1))}
            >
              ›
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-sm">
            {["日", "一", "二", "三", "四", "五", "六"].map((label) => (
              <span key={label} className="text-secondary">
                {label}
              </span>
            ))}
            {Array.from({ length: month.getDay() }, (_, i) => (
              <span key={`blank-${i}`} />
            ))}
            {Array.from({ length: days }, (_, i) => {
              const day = i + 1;
              const date = `${year}-${String(index + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
              return (
                <button
                  type="button"
                  key={day}
                  aria-label={`${year}年${index + 1}月${day}日`}
                  aria-pressed={selectedDate === date}
                  className="rounded-control p-1 hover:bg-canvas focus-visible:outline-2"
                  onClick={() => {
                    onChange(`${date} ${selectedTime}`);
                  }}
                >
                  {day}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <label>
              时{" "}
              <select
                aria-label="小时"
                className="border border-line rounded-control p-1 font-normal"
                value={hour}
                onChange={(e) => onChange(`${selectedDate} ${e.target.value}:${minute}`)}
              >
                <option value="">请选择</option>
                {Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0")).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              分{" "}
              <select
                aria-label="分钟"
                className="border border-line rounded-control p-1 font-normal"
                value={minute}
                onChange={(e) => onChange(`${selectedDate} ${hour}:${e.target.value}`)}
              >
                <option value="">请选择</option>
                {Array.from({ length: 60 }, (_, i) => String(i).padStart(2, "0")).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          </div>
          <button
            type="button"
            className="mt-3 text-sm underline"
            onClick={() => {
              setOpen(false);
              input.current?.focus();
            }}
          >
            完成
          </button>
        </div>
      )}
    </div>
  );
}
