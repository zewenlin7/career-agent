import type { Metadata } from "next";
import { Triage } from "@/features/internal/triage";
export const metadata: Metadata = { title: "Calibration & Triage" };
export default function Page() {
  return <Triage />;
}
