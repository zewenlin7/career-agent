import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Calibration & Triage" };
export default function Page() {
  return (
    <PlaceholderPage
      title="Calibration & Triage"
      description="盲标注、校准与案例分诊将在这里进行。"
    />
  );
}
