import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Runs" };
export default function Page() {
  return <PlaceholderPage title="Runs" description="单次执行的步骤、调用和结果将在这里查看。" />;
}
