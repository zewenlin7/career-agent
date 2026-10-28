import type { Metadata } from "next";
import { Incidents } from "@/features/internal/operations";
export const metadata: Metadata = { title: "Incidents & Recovery" };
export default function Page() {
  return <Incidents />;
}
