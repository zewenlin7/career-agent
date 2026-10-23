import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/layout/placeholder-page";
export const metadata: Metadata = { title: "Profile" };
export default function Page() {
  return <PlaceholderPage title="Profile" description="个人资料与已确认的事实将在这里整理。" />;
}
