"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { getAdminProfile } from "@/lib/api/dashboard";
import { searchCustomers } from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminProfile, CustomerSummary } from "@/lib/api/types";
import styles from "./PeopleList.module.css";

const PAGE_SIZE = 20;

const DATE = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

interface ListState {
  customers: CustomerSummary[];
  totalPages: number;
  page: number;
}

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "FORBIDDEN") {
      return "Your admin account does not have access to Customers.";
    }
    return error.message;
  }
  return "Couldn't load customers. Try again.";
}

export function CustomersPage() {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [query, setQuery] = useState("");
  const [list, setList] = useState<ListState | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(async (searchQuery: string, page: number) => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await searchCustomers(searchQuery, page, PAGE_SIZE);
      setList({
        customers: result.items,
        totalPages: Math.max(1, result.pagination.total_pages),
        page: result.pagination.page,
      });
    } catch (error) {
      setListError(errorMessage(error));
    } finally {
      setListLoading(false);
    }
  }, []);

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
        const result = await searchCustomers("", 1, PAGE_SIZE);
        if (ignore) return;
        setList({
          customers: result.items,
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

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Customers. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Customers…</p>
      </div>
    );
  }

  return (
    <AppShell
      title="Customers"
      subtitle="Search customer accounts"
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <form
        className={styles.searchBar}
        onSubmit={(event) => {
          event.preventDefault();
          void loadList(query, 1);
        }}
      >
        <input
          type="search"
          placeholder="Search by name…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={styles.searchInput}
          aria-label="Search customers by name"
        />
        <button type="submit" className={styles.searchButton}>
          Search
        </button>
      </form>

      {listLoading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading customers…
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
                <th>Name</th>
                <th>Status</th>
                <th>Language</th>
                <th>Joined</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {list.customers.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No customers found.
                  </td>
                </tr>
              )}
              {list.customers.map((customer) => (
                <tr key={customer.customer_id}>
                  <td>{customer.full_name}</td>
                  <td>{customer.status}</td>
                  <td>{customer.language}</td>
                  <td>{DATE.format(new Date(customer.created_at))}</td>
                  <td className={styles.actionCell}>
                    <Link
                      href={`/customers/${customer.customer_id}`}
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
              onClick={() => loadList(query, list.page - 1)}
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
              onClick={() => loadList(query, list.page + 1)}
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
