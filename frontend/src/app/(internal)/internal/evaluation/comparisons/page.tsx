import type { Metadata } from "next";
import { Comparisons } from "@/features/internal/evaluation";
export const metadata: Metadata = { title: "Comparisons" };
export default function Page() {
  return <Comparisons />;
}
