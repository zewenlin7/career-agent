import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Debriefs" };
export default function Page() {
  return <PlaceholderPage title="Debriefs" description="面试复盘与改进建议将在这里展示。" />;
}
