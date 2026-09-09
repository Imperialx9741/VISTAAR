"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { CreateFareRuleForm } from "./CreateFareRuleForm";
import { getAdminProfile } from "@/lib/api/dashboard";
import { createFareRule, listFareRules } from "@/lib/api/fare-management";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type {
  AdminProfile,
  CreateFareRuleRequest,
  FareRule,
} from "@/lib/api/types";
import styles from "./FareRulesPage.module.css";

const PAGE_SIZE = 20;
const CATEGORIES = ["", "BIKE", "AUTO", "CAB_ECO", "CAB_PREMIUM", "CAB_PREMIUM_PLUS"];
const STATUSES = ["", "DRAFT", "IN_REVIEW", "PUBLISHED"];

const CURRENCY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Fare Management.";
    }
    return error.message;
  }
  return "Couldn't load fare rules. Try again.";
}

interface ListState {
  rules: FareRule[];
  totalPages: number;
  page: number;
}

export function FareRulesPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [isCreating, setIsCreating] = useState(false);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);

  const loadList = useCallback(
    async (searchCategory: string, searchStatus: string, page: number) => {
      setListLoading(true);
      setListError(null);
      try {
        const result = await listFareRules(
          searchCategory,
          searchStatus,
          page,
          PAGE_SIZE,
        );
        setList({
          rules: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        setListError(errorMessage(error));
      } finally {
        setListLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    let ignore = false;

    async function loadProfileOnMount() {
      try {
        const result = await getAdminProfile();
        if (!ignore) setProfile(result);
      } catch {
        if (!ignore) setProfileFailed(true);
      }
    }

    async function loadListOnMount() {
      try {
        const result = await listFareRules("", "", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          rules: result.items,
          totalPages: Math.max(1, result.pagination.total_pages),
          page: result.pagination.page,
        });
      } catch (error) {
        if (!ignore) setListError(errorMessage(error));
      } finally {
        if (!ignore) setListLoading(false);
      }
    }

    loadProfileOnMount();
    loadListOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleCreate(body: CreateFareRuleRequest) {
    const created = await createFareRule(body);
    setIsCreating(false);
    setCreatedNotice(
      `Created a DRAFT ${created.vehicle_category} rule (ID ${created.rule_id}).`,
    );
    await loadList(category, status, 1);
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Fare Management. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Fare Management…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Fare Management"
      subtitle="Draft, review, and publish fare rules by vehicle category"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <div className={styles.headerRow}>
        <div className={styles.sectionLabel}>Fare rules</div>
        <div className={styles.headerActions}>
          <Link href="/fare-management/platform-fee" className={styles.viewLink}>
            Platform Fee Management →
          </Link>
          {!isCreating && (
            <button
              type="button"
              className={styles.primaryButton}
              onClick={() => {
                setCreatedNotice(null);
                setIsCreating(true);
              }}
            >
              + Create draft
            </button>
          )}
        </div>
      </div>

      {createdNotice && (
        <div className={styles.successBanner} role="status">
          {createdNotice}
        </div>
      )}

      {isCreating && (
        <div className={styles.panel}>
          <CreateFareRuleForm
            onCreate={handleCreate}
            onCancel={() => setIsCreating(false)}
          />
        </div>
      )}

      <form
        className={styles.searchBar}
        onSubmit={(event) => event.preventDefault()}
      >
        <select
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            void loadList(event.target.value, status, 1);
          }}
          className={styles.statusSelect}
          aria-label="Filter by vehicle category"
        >
          {CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any category" : value}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            void loadList(category, event.target.value, 1);
          }}
          className={styles.statusSelect}
          aria-label="Filter by status"
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value === "" ? "Any status" : value}
            </option>
          ))}
        </select>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading fare rules…
        </div>
      )}

      {!listLoading && listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      {!listLoading && !listError && list && (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Category</th>
                <th>Base</th>
                <th>Per km</th>
                <th>Minimum</th>
                <th>Status</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.rules.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No fare rules found.
                  </td>
                </tr>
              )}
              {list.rules.map((rule) => (
                <tr key={rule.rule_id}>
                  <td>{rule.vehicle_category}</td>
                  <td>{CURRENCY.format(rule.base_fare)}</td>
                  <td>{CURRENCY.format(rule.per_km)}</td>
                  <td>{CURRENCY.format(rule.minimum_fare)}</td>
                  <td>
                    <Pill tone={toneForStatus(rule.status)}>{rule.status}</Pill>
                  </td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/fare-management/${rule.rule_id}`}
                      className={styles.viewLink}
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(category, status, list.page - 1)}
              disabled={list.page <= 1}
            >
              Previous
            </button>
            <span className={styles.pageIndicator}>
              Page {list.page} of {list.totalPages}
            </span>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => loadList(category, status, list.page + 1)}
              disabled={list.page >= list.totalPages}
            >
              Next
            </button>
          </div>
        </>
      )}
    </AppShell>
  );
}
