import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Submissions" };
export default function Page() {
  return (
    <PlaceholderPage title="Submissions" description="实际投递记录与使用的材料将在这里展示。" />
  );
}
