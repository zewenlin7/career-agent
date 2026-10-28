import type { Metadata } from "next";
import { Quality } from "@/features/internal/evaluation";
export const metadata: Metadata = { title: "Production Quality" };
export default function Page() {
  return <Quality />;
}
