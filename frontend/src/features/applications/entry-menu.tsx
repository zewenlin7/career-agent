"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** A top-layer menu anchored to its trigger, including inside scrolling records. */
export function EntryMenu({
  label,
  children,
  persistent = false,
  inline = false,
}: {
  label: string;
  children: ReactNode;
  persistent?: boolean;
  inline?: boolean;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; right: number } | null>(null);
  const open = position !== null;
  useEffect(() => {
    if (!open) return;
    const align = () => {
      const button = trigger.current;
      if (!button) return;
      const rect = button.getBoundingClientRect();
      let parent = button.parentElement;
      while (parent) {
        if (getComputedStyle(parent).overflowY === "auto") {
          const bounds = parent.getBoundingClientRect();
          if (rect.bottom < bounds.top || rect.top > bounds.bottom) {
            setPosition(null);
            return;
          }
        }
        parent = parent.parentElement;
      }
      const height = menu.current?.getBoundingClientRect().height ?? 0;
      const top =
        rect.bottom + 2 + height <= window.innerHeight - 8
          ? rect.bottom + 2
          : Math.max(8, rect.top - height - 2);
      setPosition({ top, right: Math.max(8, window.innerWidth - rect.right) });
    };
    const outside = (event: PointerEvent) => {
      if (
        !trigger.current?.contains(event.target as Node) &&
        !menu.current?.contains(event.target as Node)
      )
        setPosition(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPosition(null);
        trigger.current?.focus();
      }
    };
    const frame = requestAnimationFrame(align);
    window.addEventListener("scroll", align, true);
    window.addEventListener("resize", align);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", align, true);
      window.removeEventListener("resize", align);
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={!!position}
        className={`${inline ? "shrink-0 self-start" : "absolute right-2 top-2"} rounded-control px-2 py-1 text-xl text-secondary hover:bg-surface focus:opacity-100 ${persistent || position ? "" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"}`}
        onClick={() => {
          if (position) return setPosition(null);
          const rect = trigger.current!.getBoundingClientRect();
          setPosition({ top: rect.bottom + 2, right: window.innerWidth - rect.right });
        }}
      >
        ⋮
      </button>
      {position &&
        createPortal(
          <div
            ref={menu}
            role="menu"
            aria-label={label}
            style={position}
            className="fixed z-50 w-24 rounded-control border border-line bg-paper p-1 shadow-soft"
            onClick={() => setPosition(null)}
          >
            {children}
          </div>,
          document.body,
        )}
    </>
  );
}
