import type { Metadata } from "next";
import { NewApplication } from "@/features/onboarding/jobs";
export const metadata: Metadata = { title: "新建 Job / Application" };
export default function Page() {
  return <NewApplication />;
}
