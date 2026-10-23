import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Interview Prep" };
export default function Page() {
  return (
    <PlaceholderPage title="Interview Prep" description="当前申请的面试准备内容将在这里展示。" />
  );
}
