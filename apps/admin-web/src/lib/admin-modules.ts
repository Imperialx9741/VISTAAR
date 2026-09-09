import { NAV_GROUPS } from "./nav";
import type { AdminModule } from "./api/types";

/** ADR-0040/BR-126: never grantable to an employee admin — only a Super
 * Admin ever holds implicit access to these two. Mirrors
 * modules/admin/service.py's own `_UNGRANTABLE_MODULES` frozenset;
 * kept in sync by hand since the frontend has no way to import a
 * Python enum, same as AdminModule itself (lib/api/types.ts) already
 * is. Excluding these client-side isn't a new rule — it just stops the
 * permission editor from offering a choice the backend will always
 * reject with VALIDATION_FAILED. */
const UNGRANTABLE_MODULES: ReadonlySet<AdminModule> = new Set([
  "ADMIN_MANAGEMENT",
  "SETTINGS",
]);

export interface GrantableModule {
  module: AdminModule;
  label: string;
}

/** Derived from NAV_GROUPS rather than re-listing all 20 modules by hand
 * — one source of truth for module display names, shared with the
 * sidebar. */
export const GRANTABLE_MODULES: GrantableModule[] = NAV_GROUPS.flatMap(
  (group) => group.items,
)
  .filter((item) => !UNGRANTABLE_MODULES.has(item.module))
  .map((item) => ({ module: item.module, label: item.label }));
