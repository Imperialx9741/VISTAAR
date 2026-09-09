import type { AdminModule, AdminPermission } from "./api/types";

export interface NavItem {
  label: string;
  href: string;
  module: AdminModule;
}

export interface NavGroup {
  label: string | null;
  items: NavItem[];
}

/**
 * Matches docs/15-admin-web/admin-web-implementation-plan.md §2.1's
 * grouped sidebar exactly, one item per AdminModule. Only Dashboard has a
 * real route today (app/page.tsx) — every other href is reserved so the
 * structure doesn't need to change again as each module's own screen is
 * actually built; unbuilt items render as plain (non-navigating) rows in
 * <Sidebar>.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [{ label: "Dashboard", href: "/", module: "DASHBOARD" }],
  },
  {
    label: "Operations",
    items: [
      { label: "Rides", href: "/rides", module: "RIDES" },
      { label: "Matching / Offers", href: "/matching", module: "MATCHING" },
      { label: "Safety / SOS", href: "/safety", module: "SAFETY" },
      { label: "Support / Disputes", href: "/support", module: "SUPPORT" },
    ],
  },
  {
    label: "People",
    items: [
      { label: "Customers", href: "/customers", module: "CUSTOMERS" },
      { label: "Drivers", href: "/drivers", module: "DRIVERS" },
      { label: "Vehicles", href: "/vehicles", module: "VEHICLES" },
      {
        label: "Verification / Documents",
        href: "/verification",
        module: "VERIFICATION",
      },
    ],
  },
  {
    label: "Money",
    items: [
      { label: "Finance / Wallet", href: "/finance", module: "FINANCE" },
      {
        label: "Fare Management",
        href: "/fare-management",
        module: "FARE_MANAGEMENT",
      },
      { label: "Penalties / Strikes", href: "/penalties", module: "PENALTIES" },
      {
        label: "Offers / Coupons",
        href: "/offers-coupons",
        module: "OFFERS_COUPONS",
      },
      { label: "Referrals", href: "/referrals", module: "REFERRALS" },
    ],
  },
  {
    label: "Growth",
    items: [
      {
        label: "Advertisements",
        href: "/advertisements",
        module: "ADVERTISEMENTS",
      },
      { label: "Notifications", href: "/notifications", module: "NOTIFICATIONS" },
    ],
  },
  {
    label: "Insights",
    items: [
      { label: "Reports / Analytics", href: "/reports", module: "REPORTS" },
      { label: "Audit Logs", href: "/audit-logs", module: "AUDIT_LOGS" },
    ],
  },
  {
    label: "System",
    items: [
      {
        label: "Admin Management",
        href: "/admin-management",
        module: "ADMIN_MANAGEMENT",
      },
      { label: "Settings", href: "/settings", module: "SETTINGS" },
    ],
  },
];

/**
 * A Super Admin sees every item, no permission rows needed (ADR-0040 —
 * implicit full access). An employee admin sees only what they hold at
 * least VIEW on, matching the plan's own §2.2 client-side gating rule (the
 * real enforcement is still server-side on every route regardless).
 */
export function isModuleVisible(
  module: AdminModule,
  role: string,
  permissions: AdminPermission[],
): boolean {
  if (role === "SUPER_ADMIN") return true;
  return permissions.some(
    (permission) => permission.module === module,
  );
}
