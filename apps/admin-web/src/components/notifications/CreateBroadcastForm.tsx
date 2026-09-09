"use client";

import { useState } from "react";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type {
  BroadcastAudienceType,
  CreateBroadcastRequest,
  NotificationChannel,
} from "@/lib/api/types";
import styles from "./BroadcastsPage.module.css";

// WHATSAPP excluded — the backend rejects it outright (no BSP chosen
// yet, ADR-0034 Decision 3, unaffected by ADR-0055).
const CHANNELS: NotificationChannel[] = ["IN_APP", "SMS", "PUSH"];

const AUDIENCE_TYPES: { value: BroadcastAudienceType; label: string }[] = [
  { value: "ALL_CUSTOMERS", label: "All customers" },
  { value: "ALL_DRIVERS", label: "All drivers" },
  { value: "ONLINE_DRIVERS", label: "Online drivers" },
  { value: "SELECTED", label: "Selected users" },
];

interface CreateBroadcastFormProps {
  onCreate: (body: CreateBroadcastRequest) => Promise<void>;
  onCancel: () => void;
}

function messageFor(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Couldn't send the broadcast. Try again.";
}

/** Compose/Send Broadcast + Audience Selection (ADR-0055 Tier C). A
 * broadcast carries its own free-text subject/body — under the hood
 * this publishes a broadcast-only Template, but the admin never sees
 * that; they compose here directly. */
export function CreateBroadcastForm({
  onCreate,
  onCancel,
}: CreateBroadcastFormProps) {
  const [channel, setChannel] = useState<NotificationChannel>("IN_APP");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [audienceType, setAudienceType] =
    useState<BroadcastAudienceType>("ALL_CUSTOMERS");
  const [audienceUserIds, setAudienceUserIds] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedIds = audienceUserIds
    .split(/[\n,]/)
    .map((id) => id.trim())
    .filter(Boolean);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate({
        channel,
        subject: subject.trim() || null,
        body: body.trim(),
        audience_type: audienceType,
        audience_user_ids: audienceType === "SELECTED" ? selectedIds : null,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
      });
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  const canSubmit =
    body.trim().length > 0 &&
    (audienceType !== "SELECTED" || selectedIds.length > 0);

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.formGrid}>
        <div className={styles.field}>
          <label htmlFor="broadcast-channel" className={styles.label}>
            Channel
          </label>
          <select
            id="broadcast-channel"
            value={channel}
            onChange={(event) =>
              setChannel(event.target.value as NotificationChannel)
            }
            disabled={isSubmitting}
            className={styles.select}
          >
            {CHANNELS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="broadcast-audience" className={styles.label}>
            Audience
          </label>
          <select
            id="broadcast-audience"
            value={audienceType}
            onChange={(event) =>
              setAudienceType(event.target.value as BroadcastAudienceType)
            }
            disabled={isSubmitting}
            className={styles.select}
          >
            {AUDIENCE_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="broadcast-scheduled-at" className={styles.label}>
            Send at (leave blank to send now)
          </label>
          <input
            id="broadcast-scheduled-at"
            type="datetime-local"
            value={scheduledAt}
            onChange={(event) => setScheduledAt(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={`${styles.field} ${styles.fieldWide}`}>
          <label htmlFor="broadcast-subject" className={styles.label}>
            Subject (optional)
          </label>
          <input
            id="broadcast-subject"
            type="text"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
      </div>

      {audienceType === "SELECTED" && (
        <div className={styles.field}>
          <label htmlFor="broadcast-audience-ids" className={styles.label}>
            Recipient user IDs
          </label>
          <textarea
            id="broadcast-audience-ids"
            rows={3}
            placeholder="One customer/driver ID per line, or comma-separated"
            value={audienceUserIds}
            onChange={(event) => setAudienceUserIds(event.target.value)}
            disabled={isSubmitting}
            className={styles.textarea}
          />
          <span className={styles.hint}>
            {selectedIds.length} recipient{selectedIds.length === 1 ? "" : "s"}
          </span>
        </div>
      )}

      <div className={styles.field}>
        <label htmlFor="broadcast-body" className={styles.label}>
          Message
        </label>
        <textarea
          id="broadcast-body"
          required
          rows={4}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          disabled={isSubmitting}
          className={styles.input}
        />
      </div>

      {error && (
        <div className={styles.errorBanner} role="alert">
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
          disabled={isSubmitting || !canSubmit}
        >
          {isSubmitting
            ? "Sending…"
            : scheduledAt
              ? "Schedule broadcast"
              : "Send now"}
        </button>
      </div>
    </form>
  );
}
