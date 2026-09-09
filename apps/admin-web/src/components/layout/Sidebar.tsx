"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { NAV_GROUPS, isModuleVisible } from "@/lib/nav";
import type { AdminPermission } from "@/lib/api/types";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  role: string;
  permissions: AdminPermission[];
  /** Modules with a real screen built so far — everything else renders
   * as a disabled row rather than a dead link, so the nav's full shape
   * is visible without pretending unbuilt screens exist. */
  builtHrefs: Set<string>;
}

export function Sidebar({ role, permissions, builtHrefs }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className={styles.sidebar} aria-label="Primary">
      <div className={styles.brand}>
        <div className={styles.brandMark} aria-hidden="true">
          V
        </div>
        <div>
          <div className={styles.brandName}>VISTAAR</div>
          <div className={styles.brandSub}>Admin Console</div>
        </div>
      </div>

      <nav className={styles.groups}>
        {NAV_GROUPS.map((group) => {
          const visibleItems = group.items.filter((item) =>
            isModuleVisible(item.module, role, permissions),
          );
          if (visibleItems.length === 0) return null;

          return (
            <div className={styles.navGroup} key={group.label ?? "root"}>
              {group.label && (
                <div className={styles.navGroupLabel}>{group.label}</div>
              )}
              {visibleItems.map((item) => {
                const isActive = pathname === item.href;
                const isBuilt = builtHrefs.has(item.href);

                if (!isBuilt) {
                  return (
                    <span
                      key={item.href}
                      className={`${styles.navItem} ${styles.navItemDisabled}`}
                      title="Not built yet"
                    >
                      <span className={styles.dot} aria-hidden="true" />
                      {item.label}
                    </span>
                  );
                }

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`${styles.navItem} ${
                      isActive ? styles.navItemActive : ""
                    }`}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <span className={styles.dot} aria-hidden="true" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
