import Link from "next/link";
import type { ReactNode } from "react";
import { Navigation } from "./navigation";
import { internalNavigation, productNavigation } from "@/lib/navigation";

export function AppShell({
  mode,
  children,
}: {
  mode: "product" | "internal";
  children: ReactNode;
}) {
  const internal = mode === "internal";
  return (
    <div className="min-h-dvh">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-control focus:bg-paper focus:p-3"
      >
        跳到主要内容
      </a>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex min-h-[58px] max-w-[1200px] flex-wrap items-center gap-x-8 gap-y-2 px-5 py-3 sm:px-6">
          <Link
            href={internal ? "/internal/operations/overview" : "/applications"}
            className="font-serif text-[17px] font-semibold tracking-[-0.3px]"
          >
            Career Agent
          </Link>
          <Navigation
            items={internal ? internalNavigation : productNavigation}
            label={internal ? "Internal 主导航" : "Product 主导航"}
          />
          <Link
            href={internal ? "/applications" : "/internal/operations/overview"}
            className="ml-auto inline-flex min-h-11 items-center rounded-control px-2 text-sm text-secondary underline-offset-4 hover:text-accent-ink hover:underline"
          >
            {internal ? "返回 Applications" : "Internal"}
          </Link>
        </div>
      </header>
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto max-w-[1200px] px-5 py-7 focus:outline-none sm:px-6 sm:py-10"
      >
        {children}
      </main>
    </div>
  );
}
