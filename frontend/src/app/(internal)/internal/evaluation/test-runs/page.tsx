import type { Metadata } from "next";
import { TestRuns } from "@/features/internal/evaluation";
export const metadata: Metadata = { title: "Test Runs" };
export default function Page() {
  return <TestRuns />;
}
