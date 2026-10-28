import type { Metadata } from "next";
import { Runs } from "@/features/internal/operations";
export const metadata: Metadata = { title: "Runs" };
export default function Page() {
  return <Runs />;
}
