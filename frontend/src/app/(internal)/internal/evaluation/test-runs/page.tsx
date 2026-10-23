import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Test Runs" };
export default function Page() {
  return <PlaceholderPage title="Test Runs" description="评估套件、运行与试验记录将在这里查看。" />;
}
