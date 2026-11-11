"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { isActivePath, type NavigationItem } from "@/lib/navigation";
import { cx } from "@/lib/styles";

export function Navigation({ items, label }: { items: NavigationItem[]; label: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label={label}>
      <ul className="flex flex-wrap items-center gap-1">
        {items.map((item) => (
          <li key={item.href}>
            {item.children ? (
              <NavigationMenu item={item} pathname={pathname} />
            ) : (
              <Link
                href={item.href}
                prefetch={false}
                aria-current={isActivePath(pathname, item) ? "page" : undefined}
                className={cx(
                  "inline-flex min-h-11 items-center rounded-control px-3 py-2 text-sm transition-colors",
                  isActivePath(pathname, item)
                    ? "bg-paper text-accent-ink shadow-soft"
                    : "text-secondary hover:bg-paper/60 hover:text-ink",
                )}
              >
                {item.label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

function NavigationMenu({ item, pathname }: { item: NavigationItem; pathname: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  const focusItem = (index: number) => {
    const links = root.current?.querySelectorAll<HTMLAnchorElement>('[role="menuitem"]');
    if (links?.length) links[(index + links.length) % links.length].focus();
  };
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  useEffect(() => {
    if (open && keyboardOpen) focusItem(0);
  }, [open, keyboardOpen]);
  return (
    <div
      ref={root}
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        className={cx(
          "inline-flex min-h-11 items-center gap-1 rounded-control px-3 py-2 text-sm",
          isActivePath(pathname, item)
            ? "bg-paper text-accent-ink shadow-soft"
            : "text-secondary hover:bg-paper/60",
        )}
        onClick={() => {
          setKeyboardOpen(false);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setKeyboardOpen(true);
            setOpen(true);
            if (open) focusItem(0);
          }
        }}
      >
        {item.label}
        <span aria-hidden="true" className="text-xs">
          ▾
        </span>
      </button>
      {open && (
        <div className="absolute left-0 top-full z-40 min-w-36 pt-1">
          <ul
            role="menu"
            aria-label={item.label}
            className="rounded-control border border-line bg-paper py-1 shadow-soft"
            onKeyDown={(e) => {
              const links = [...(root.current?.querySelectorAll('[role="menuitem"]') || [])];
              const index = links.indexOf(document.activeElement!);
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                focusItem(index + (e.key === "ArrowDown" ? 1 : -1));
              }
              if (e.key === "Home" || e.key === "End") {
                e.preventDefault();
                focusItem(e.key === "Home" ? 0 : -1);
              }
            }}
          >
            {item.children?.map((child) => (
              <li key={child.href} role="none">
                <Link
                  role="menuitem"
                  prefetch={false}
                  href={child.href}
                  aria-current={pathname === child.href ? "page" : undefined}
                  onClick={() => setOpen(false)}
                  className={cx(
                    "block whitespace-nowrap px-3 py-2 text-sm font-normal hover:bg-surface focus-visible:bg-surface",
                    pathname === child.href ? "text-accent-ink" : "text-secondary",
                  )}
                >
                  {child.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
