import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Resume" };
export default function Page() {
  return <PlaceholderPage title="Resume" description="为当前申请准备的简历与 PDF 将在这里展示。" />;
}
