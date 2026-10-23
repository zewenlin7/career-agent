import type { ReactNode } from "react";
import { Navigation } from "@/components/layout/navigation";
import { evaluationNavigation } from "@/lib/navigation";
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <div className="mb-8 border-b border-line pb-4">
        <Navigation items={evaluationNavigation} label="Evaluation 导航" />
      </div>
      {children}
    </>
  );
}
