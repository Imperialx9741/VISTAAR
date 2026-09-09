import type { ReactNode } from "react";
import styles from "./StatCard.module.css";

type Severity = "neutral" | "info" | "success" | "warning" | "danger";

interface StatCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  severity?: Severity;
  /** Renders the "not available yet" muted treatment instead of a
   * number — used by widgets the backend doesn't return yet (e.g.
   * Online Drivers). Never fabricates a number to fill the slot. */
  unavailable?: boolean;
  highlight?: boolean;
}

export function StatCard({
  label,
  value,
  sub,
  severity = "neutral",
  unavailable = false,
  highlight = false,
}: StatCardProps) {
  return (
    <div
      className={`${styles.card} ${highlight ? styles.highlight : ""}`}
    >
      {!highlight && (
        <div className={`${styles.stripe} ${styles[severity]}`} aria-hidden="true" />
      )}
      <div className={styles.label}>{label}</div>
      <div className={`${styles.value} ${unavailable ? styles.unavailable : ""}`}>
        {value}
      </div>
      {sub && <div className={styles.sub}>{sub}</div>}
    </div>
  );
}
