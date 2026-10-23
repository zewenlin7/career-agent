import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Record Actual Interview" };
export default function Page() {
  return (
    <PlaceholderPage
      title="Record Actual Interview"
      description="真实面试的问题、回答与笔记将在这里录入。"
    />
  );
}
