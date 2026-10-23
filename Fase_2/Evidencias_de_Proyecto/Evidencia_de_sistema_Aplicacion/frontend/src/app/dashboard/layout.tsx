import type { ReactNode } from "react";
import DashboardAuthGate from "./DashboardAuthGate";
import DashboardShell from "@/components/dashboard/DashboardShell";
import { DossierJobsProvider } from "@/providers/DossierJobsProvider";
import { NotificationsProvider } from "@/providers/NotificationsProvider";

export default function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <DashboardAuthGate>
      <NotificationsProvider>
        <DossierJobsProvider>
          <DashboardShell>{children}</DashboardShell>
        </DossierJobsProvider>
      </NotificationsProvider>
    </DashboardAuthGate>
  );
}
