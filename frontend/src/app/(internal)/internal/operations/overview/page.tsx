import type { Metadata } from "next";
import { Overview } from "@/features/internal/operations";
export const metadata: Metadata = { title: "Overview" };
export default function Page() {
  return <Overview />;
}
