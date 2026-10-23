"use client";

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
          </li>
        ))}
      </ul>
    </nav>
  );
}
