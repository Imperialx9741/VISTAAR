import { apiGet, apiPost } from "./client";
import type {
  CustomerRewardRule,
  DriverBonusRule,
  PaginatedEnvelope,
  Referral,
} from "./types";

/**
 * Referrals (api-contracts.md §46.6 search, §46.12 reward
 * configuration, ADR-0043, Admin Web §4.11). No sample-data fallback,
 * same rule as every other operational screen in this app.
 */

export function searchReferrals(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Referral>> {
  return apiGet<PaginatedEnvelope<Referral>>("/api/v1/admin/referrals", {
    status: status || undefined,
    page,
    page_size: pageSize,
  });
}

export function listDriverBonusRules(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<DriverBonusRule>> {
  return apiGet<PaginatedEnvelope<DriverBonusRule>>(
    "/api/v1/admin/referral-config/driver-bonus",
    { status: status || undefined, page, page_size: pageSize },
  );
}

export function getDriverBonusRule(ruleId: string): Promise<DriverBonusRule> {
  return apiGet<DriverBonusRule>(
    `/api/v1/admin/referral-config/driver-bonus/${ruleId}`,
  );
}

export function createDriverBonusRule(
  referredAmount: number,
  referrerAmount: number,
): Promise<DriverBonusRule> {
  return apiPost<DriverBonusRule>("/api/v1/admin/referral-config/driver-bonus", {
    referred_amount: referredAmount,
    referrer_amount: referrerAmount,
  });
}

export function submitDriverBonusRuleForReview(
  ruleId: string,
): Promise<DriverBonusRule> {
  return apiPost<DriverBonusRule>(
    `/api/v1/admin/referral-config/driver-bonus/${ruleId}/submit-for-review`,
    {},
  );
}

export function publishDriverBonusRule(
  ruleId: string,
  effectiveFrom?: string,
): Promise<DriverBonusRule> {
  return apiPost<DriverBonusRule>(
    `/api/v1/admin/referral-config/driver-bonus/${ruleId}/publish`,
    { effective_from: effectiveFrom || undefined },
  );
}

export function listCustomerRewardRules(
  rewardType: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<CustomerRewardRule>> {
  return apiGet<PaginatedEnvelope<CustomerRewardRule>>(
    "/api/v1/admin/referral-config/customer-rewards",
    {
      reward_type: rewardType || undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  );
}

export function getCustomerRewardRule(
  ruleId: string,
): Promise<CustomerRewardRule> {
  return apiGet<CustomerRewardRule>(
    `/api/v1/admin/referral-config/customer-rewards/${ruleId}`,
  );
}

export function createCustomerRewardRule(
  rewardType: string,
  discountPercent: number,
  totalUses: number,
): Promise<CustomerRewardRule> {
  return apiPost<CustomerRewardRule>(
    "/api/v1/admin/referral-config/customer-rewards",
    {
      reward_type: rewardType,
      discount_percent: discountPercent,
      total_uses: totalUses,
    },
  );
}

export function submitCustomerRewardRuleForReview(
  ruleId: string,
): Promise<CustomerRewardRule> {
  return apiPost<CustomerRewardRule>(
    `/api/v1/admin/referral-config/customer-rewards/${ruleId}/submit-for-review`,
    {},
  );
}

export function publishCustomerRewardRule(
  ruleId: string,
  effectiveFrom?: string,
): Promise<CustomerRewardRule> {
  return apiPost<CustomerRewardRule>(
    `/api/v1/admin/referral-config/customer-rewards/${ruleId}/publish`,
    { effective_from: effectiveFrom || undefined },
  );
}
