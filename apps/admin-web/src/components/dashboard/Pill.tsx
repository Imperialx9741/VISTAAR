import styles from "./Pill.module.css";

type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "gold";

export function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: Tone;
}) {
  return <span className={`${styles.pill} ${styles[tone]}`}>{children}</span>;
}
