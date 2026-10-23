import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Mock Interview" };
export default function Page() {
  return <PlaceholderPage title="Mock Interview" description="模拟面试将从这里开始。" />;
}
