import type { Metadata } from "next";
import { Controls } from "@/features/internal/operations";
export const metadata: Metadata = { title: "Controls" };
export default function Page() {
  return <Controls />;
}
