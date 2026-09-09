"use client";

import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import type { AdminPermission } from "@/lib/api/types";
import styles from "./AppShell.module.css";

const BUILT_HREFS = new Set<string>([
  "/",
  "/admin-management",
  "/customers",
  "/drivers",
  "/vehicles",
  "/verification",
  "/audit-logs",
  "/fare-management",
  "/offers-coupons",
  "/safety",
  "/support",
  "/notifications",
  "/referrals",
  "/advertisements",
  "/reports",
  "/settings",
  "/rides",
  "/finance",
  "/penalties",
  "/matching",
]);

interface AppShellProps {
  title: string;
  subtitle?: string;
  adminRole: string;
  adminPermissions: AdminPermission[];
  children: ReactNode;
}

export function AppShell({
  title,
  subtitle,
  adminRole,
  adminPermissions,
  children,
}: AppShellProps) {
  const initials = adminRole === "SUPER_ADMIN" ? "SA" : "A";

  return (
    <div className={styles.shell}>
      <div className={styles.sidebarSlot}>
        <Sidebar
          role={adminRole}
          permissions={adminPermissions}
          builtHrefs={BUILT_HREFS}
        />
      </div>
      <div className={styles.main}>
        <TopBar
          title={title}
          subtitle={subtitle}
          adminRole={adminRole}
          adminInitials={initials}
        />
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
