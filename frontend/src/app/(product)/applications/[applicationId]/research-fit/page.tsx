import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Research & Fit" };
export default function Page() {
  return (
    <PlaceholderPage
      title="Research & Fit"
      description="公司研究、职位要求和匹配分析将在这里展示。"
    />
  );
}
