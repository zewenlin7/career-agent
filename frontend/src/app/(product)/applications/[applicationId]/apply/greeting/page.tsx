import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Greeting" };
export default function Page() {
  return <PlaceholderPage title="Greeting" description="招呼语与生成历史将在这里展示。" />;
}
