import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Knowledge Notes" };
export default function Page() {
  return (
    <PlaceholderPage title="Knowledge Notes" description="与当前申请关联的知识笔记将在这里整理。" />
  );
}
