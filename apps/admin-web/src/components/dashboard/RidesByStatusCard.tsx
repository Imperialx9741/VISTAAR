import styles from "./RidesByStatusCard.module.css";

/** Real RideStatus values only (modules/ride/domain/entities.py) — order
 * here is the ride lifecycle's own order, not alphabetical, so the list
 * reads as a story rather than a shuffled table. */
const STATUS_ORDER = [
  "SEARCHING",
  "ACCEPTED",
  "ARRIVED",
  "STARTED",
  "COMPLETED",
  "CLOSED",
  "CANCELLED",
] as const;

const STATUS_LABEL: Record<string, string> = {
  SEARCHING: "Searching for a driver",
  ACCEPTED: "Accepted",
  ARRIVED: "Driver arrived",
  STARTED: "In progress",
  COMPLETED: "Completed",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
};

const STATUS_COLOR_VAR: Record<string, string> = {
  SEARCHING: "var(--warning)",
  ACCEPTED: "var(--info)",
  ARRIVED: "var(--info)",
  STARTED: "var(--info)",
  COMPLETED: "var(--success)",
  CLOSED: "var(--success)",
  CANCELLED: "var(--danger)",
};

interface RidesByStatusCardProps {
  byStatus: Record<string, number>;
}

export function RidesByStatusCard({ byStatus }: RidesByStatusCardProps) {
  const total = Object.values(byStatus).reduce((sum, n) => sum + n, 0);
  const orderedStatuses = STATUS_ORDER.filter((status) => byStatus[status]);

  return (
    <div className={styles.card}>
      <h2 className={styles.heading}>Today&apos;s rides, by status</h2>
      <p className={styles.note}>Requested since midnight, IST</p>

      {total === 0 ? (
        <p className={styles.empty}>No rides requested yet today.</p>
      ) : (
        <>
          <div className={styles.barTrack}>
            {orderedStatuses.map((status) => (
              <div
                key={status}
                className={styles.barSeg}
                style={{
                  width: `${(byStatus[status] / total) * 100}%`,
                  background: STATUS_COLOR_VAR[status],
                }}
                title={`${STATUS_LABEL[status]}: ${byStatus[status]}`}
              />
            ))}
          </div>

          <dl className={styles.rows}>
            {orderedStatuses.map((status) => (
              <div className={styles.row} key={status}>
                <dt className={styles.rowLabel}>
                  <span
                    className={styles.dot}
                    style={{ background: STATUS_COLOR_VAR[status] }}
                    aria-hidden="true"
                  />
                  {STATUS_LABEL[status]}
                </dt>
                <dd className={styles.rowValue}>{byStatus[status]}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </div>
  );
}
