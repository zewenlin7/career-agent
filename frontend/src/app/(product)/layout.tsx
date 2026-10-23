import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/app-shell";
export default function ProductLayout({ children }: { children: ReactNode }) {
  return <AppShell mode="product">{children}</AppShell>;
}
