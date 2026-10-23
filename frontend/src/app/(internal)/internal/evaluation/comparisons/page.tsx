import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Comparisons" };
export default function Page() {
  return <PlaceholderPage title="Comparisons" description="评估运行之间的比较将在这里展示。" />;
}
