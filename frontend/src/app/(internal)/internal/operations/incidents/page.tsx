import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Incidents & Recovery" };
export default function Page() {
  return (
    <PlaceholderPage
      title="Incidents & Recovery"
      description="需要关注的执行状态与恢复事项将在这里展示。"
    />
  );
}
