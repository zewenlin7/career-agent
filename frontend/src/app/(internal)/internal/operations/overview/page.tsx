import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Overview" };
export default function Page() {
  return <PlaceholderPage title="Overview" description="运行健康与资源使用的汇总将在这里展示。" />;
}
