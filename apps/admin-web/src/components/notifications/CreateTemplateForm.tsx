"use client";

import { useState } from "react";
import { ApiError, NoSessionError } from "@/lib/api/client";
import type { CreateTemplateRequest, NotificationChannel } from "@/lib/api/types";
import styles from "./TemplatesPage.module.css";

const CHANNELS: NotificationChannel[] = ["IN_APP", "SMS", "PUSH", "WHATSAPP"];

interface CreateTemplateFormProps {
  onCreate: (body: CreateTemplateRequest) => Promise<void>;
  onCancel: () => void;
}

function messageFor(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Couldn't create the template. Try again.";
}

/** Create Draft notification template (ADR-0044). There is no separate
 * Edit endpoint — this same form, resubmitted with the same
 * (template_key, channel), always creates the next version. */
export function CreateTemplateForm({
  onCreate,
  onCancel,
}: CreateTemplateFormProps) {
  const [templateKey, setTemplateKey] = useState("");
  const [channel, setChannel] = useState<NotificationChannel>("SMS");
  const [eventKey, setEventKey] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate({
        template_key: templateKey.trim(),
        channel,
        event_key: eventKey.trim() || null,
        title: title.trim() || null,
        body: body.trim(),
      });
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.formGrid}>
        <div className={styles.field}>
          <label htmlFor="template-key" className={styles.label}>
            Template key
          </label>
          <input
            id="template-key"
            type="text"
            required
            placeholder="RIDE_ACCEPTED"
            value={templateKey}
            onChange={(event) => setTemplateKey(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="template-channel" className={styles.label}>
            Channel
          </label>
          <select
            id="template-channel"
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
          <label htmlFor="template-event-key" className={styles.label}>
            Event key (optional)
          </label>
          <input
            id="template-event-key"
            type="text"
            placeholder="ride.accepted"
            value={eventKey}
            onChange={(event) => setEventKey(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="template-title" className={styles.label}>
            Title (optional)
          </label>
          <input
            id="template-title"
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>
      </div>

      <div className={styles.field}>
        <label htmlFor="template-body" className={styles.label}>
          Body
        </label>
        <textarea
          id="template-body"
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
          disabled={isSubmitting || !templateKey.trim() || !body.trim()}
        >
          {isSubmitting ? "Creating…" : "Create draft"}
        </button>
      </div>
    </form>
  );
}
