import type { Metadata } from "next";
import { NewApplication } from "@/features/onboarding/jobs";
export const metadata: Metadata = { title: "新建申请" };
export default function Page() {
  return <NewApplication />;
}
