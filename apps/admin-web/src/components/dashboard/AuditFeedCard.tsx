import type { AuditLogEntry } from "@/lib/api/types";
import styles from "./AuditFeedCard.module.css";

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} d ago`;
}

function actionLabel(action: string): string {
  return action
    .toLowerCase()
    .split("_")
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(" ");
}

interface AuditFeedCardProps {
  entries: AuditLogEntry[];
}

export function AuditFeedCard({ entries }: AuditFeedCardProps) {
  return (
    <div className={styles.card}>
      <h2 className={styles.heading}>Latest audit entries</h2>
      <p className={styles.note}>From admin.audit_logs, newest first</p>

      {entries.length === 0 ? (
        <p className={styles.empty}>No admin actions recorded yet.</p>
      ) : (
        <ul className={styles.list}>
          {entries.map((entry) => (
            <li className={styles.item} key={entry.id}>
              <div>
                <div className={styles.who}>{actionLabel(entry.action)}</div>
                <div className={styles.what}>
                  {entry.target_type
                    ? `${entry.target_type.toLowerCase()}${
                        entry.target_id ? ` · ${entry.target_id.slice(0, 8)}…` : ""
                      }`
                    : "—"}
                </div>
              </div>
              <div className={styles.when}>{relativeTime(entry.created_at)}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
