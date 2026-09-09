import { apiGet, apiPatch } from "./client";
import type { Setting } from "./types";

/**
 * Settings (api-contracts.md §46.17, ADR-0048, Admin Web §4.19).
 * `GET /settings` returns a bare array, not a paginated envelope — the
 * key set is fixed and small by design (Decision 2), so there's
 * nothing to page through. No Create/Delete — PATCH is the only
 * mutation (Decision 3).
 */

export function listSettings(category: string): Promise<Setting[]> {
  return apiGet<Setting[]>("/api/v1/admin/settings", {
    category: category || undefined,
  });
}

export function getSetting(key: string): Promise<Setting> {
  return apiGet<Setting>(`/api/v1/admin/settings/${key}`);
}

export function updateSetting(key: string, value: unknown): Promise<Setting> {
  return apiPatch<Setting>(`/api/v1/admin/settings/${key}`, { value });
}
