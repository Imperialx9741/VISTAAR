import { apiGet } from "./client";
import type { DriverWallet, PaginatedEnvelope, WalletTransaction } from "./types";

/**
 * Finance / Wallet (api-contracts.md §34/§47, Admin Web §4.7).
 * Read-only — a wallet is looked up by a known driver_id, there is no
 * search-all-wallets endpoint by design.
 */

export function getDriverWallet(driverId: string): Promise<DriverWallet> {
  return apiGet<DriverWallet>(`/api/v1/admin/wallets/${driverId}`);
}

export function listDriverWalletTransactions(
  driverId: string,
  type: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<WalletTransaction>> {
  return apiGet<PaginatedEnvelope<WalletTransaction>>(
    `/api/v1/admin/wallets/${driverId}/transactions`,
    { type: type || undefined, page, page_size: pageSize },
  );
}
