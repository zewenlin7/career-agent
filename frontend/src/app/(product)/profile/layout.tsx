import type { ReactNode } from "react";
import { ProfileNavigation } from "@/features/profile-area/navigation";
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <ProfileNavigation />
      {children}
    </>
  );
}
