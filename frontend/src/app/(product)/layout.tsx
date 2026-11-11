import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { TaskNotifications } from "@/features/workspace/task-notifications";
export default function ProductLayout({ children }: { children: ReactNode }) {
  return (
    <AppShell mode="product">
      <TaskNotifications />
      {children}
    </AppShell>
  );
}
