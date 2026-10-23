import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Controls" };
export default function Page() {
  return <PlaceholderPage title="Controls" description="现有管理员控制操作将在这里接入。" />;
}
