import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Previous Interviews" };
export default function Page() {
  return (
    <PlaceholderPage
      title="Previous Interviews"
      description="过去的模拟面试与真实面试将在这里查看。"
    />
  );
}
