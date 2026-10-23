import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Production Quality" };
export default function Page() {
  return (
    <PlaceholderPage title="Production Quality" description="生产运行的质量信号将在这里展示。" />
  );
}
