"use client";

import { useState } from "react";
import { PermissionEditor } from "./PermissionEditor";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { AdminPermission } from "@/lib/api/types";
import styles from "./CreateAdminForm.module.css";

interface CreateAdminFormProps {
  onCreate: (phone: string, permissions: AdminPermission[]) => Promise<void>;
  onCancel: () => void;
}

function messageFor(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) {
    // VALIDATION_FAILED here is almost always "phone already provisioned"
    // (api-contracts.md §46.1) — the backend message already says which.
    return error.message;
  }
  return "Couldn't create the admin. Try again.";
}

/** Create Employee Admin (ADR-0040). The account authenticates through
 * the ordinary phone+OTP flow — no password/credential is collected or
 * generated here, matching what the backend itself does. */
export function CreateAdminForm({ onCreate, onCancel }: CreateAdminFormProps) {
  const [phone, setPhone] = useState("");
  const [permissions, setPermissions] = useState<AdminPermission[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate(phone.trim(), permissions);
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.field}>
        <label htmlFor="admin-phone" className={styles.label}>
          Phone number
        </label>
        <input
          id="admin-phone"
          type="tel"
          required
          placeholder="+91XXXXXXXXXX"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          disabled={isSubmitting}
          className={styles.input}
        />
      </div>

      <div className={styles.field}>
        <div className={styles.label}>Module access</div>
        <p className={styles.hint}>
          Leave everything on None to create the admin with no access yet
          — permissions can be changed later from their profile.
        </p>
        <PermissionEditor
          value={permissions}
          onChange={setPermissions}
          disabled={isSubmitting}
        />
      </div>

      {error && (
        <div className={styles.error} role="alert">
          {error}
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className={styles.primaryButton}
          disabled={isSubmitting || phone.trim().length === 0}
        >
          {isSubmitting ? "Creating…" : "Create admin"}
        </button>
      </div>
    </form>
  );
}
