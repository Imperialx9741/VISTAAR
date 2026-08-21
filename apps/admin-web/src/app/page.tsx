import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.container}>
      <main className={styles.main}>
        <h1 className={styles.title}>VISTAAR Admin</h1>
        <p className={styles.subtitle}>Initial Application Skeleton</p>
      </main>
    </div>
  );
}
