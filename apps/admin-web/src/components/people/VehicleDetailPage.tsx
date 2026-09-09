"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Pill } from "@/components/dashboard/Pill";
import { getAdminProfile } from "@/lib/api/dashboard";
import {
  approveVehicle,
  getVehicle,
  listVehicleDocuments,
  rejectVehicle,
} from "@/lib/api/people";
import { ApiError, NoSessionError } from "@/lib/api/client";
import { toneForStatus } from "@/lib/status-tone";
import type { AdminProfile, Vehicle, VehicleDocument } from "@/lib/api/types";
import styles from "./PeopleDetail.module.css";

function errorMessage(error: unknown): string {
  if (error instanceof NoSessionError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Try again.";
}

export function VehicleDetailPage({ vehicleId }: { vehicleId: string }) {
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);

  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [documents, setDocuments] = useState<VehicleDocument[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [documentsLoading, setDocumentsLoading] = useState(true);

  const [rejectReason, setRejectReason] = useState("");
  const [showRejectField, setShowRejectField] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

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

    async function loadVehicleOnMount() {
      try {
        const data = await getVehicle(vehicleId);
        if (!ignore) setVehicle(data);
      } catch (error) {
        if (!ignore) setLoadError(errorMessage(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    // Independent from the vehicle load above — Vehicle Documents is
    // gated under the VERIFICATION module, not VEHICLES (api-contracts.md
    // §46.4), so an admin can legitimately see the vehicle itself but not
    // its documents. A failure here only blanks this section, not the
    // whole page.
    async function loadDocumentsOnMount() {
      try {
        const data = await listVehicleDocuments(vehicleId);
        if (!ignore) setDocuments(data);
      } catch (error) {
        if (!ignore) setDocumentsError(errorMessage(error));
      } finally {
        if (!ignore) setDocumentsLoading(false);
      }
    }

    loadProfileOnMount();
    loadVehicleOnMount();
    loadDocumentsOnMount();
    return () => {
      ignore = true;
    };
  }, [vehicleId]);

  async function runAction(label: string, action: () => Promise<Vehicle>) {
    setIsWorking(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await action();
      setVehicle(updated);
      setActionSuccess(label);
      setShowRejectField(false);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setIsWorking(false);
    }
  }

  if (profileFailed) {
    return (
      <div className={styles.fullPageMessage}>
        <p>Something went wrong loading Vehicles. Try reloading.</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={styles.fullPageMessage} role="status" aria-live="polite">
        <p>Loading Vehicles…</p>
      </div>
    );
  }

  const canApproveOrReject = vehicle?.verification_status === "PENDING";

  return (
    <AppShell
      title="Vehicle profile"
      subtitle={vehicleId}
      adminRole={profile.role}
      adminPermissions={profile.permissions}
    >
      <Link href="/vehicles" className={styles.backLink}>
        ← Back to Vehicles
      </Link>

      {loading && (
        <div className={styles.stateMessage} role="status" aria-live="polite">
          Loading vehicle…
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      )}

      {!loading && !loadError && vehicle && (
        <>
          <div className={styles.summaryCard}>
            <div>
              <div className={styles.summaryLabel}>Registration</div>
              <div className={styles.summaryValue}>
                {vehicle.registration_number}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Category</div>
              <div className={styles.summaryValue}>{vehicle.category}</div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Make / Model</div>
              <div className={styles.summaryValue}>
                {vehicle.make} {vehicle.model}
              </div>
            </div>
            <div>
              <div className={styles.summaryLabel}>Verification</div>
              <Pill tone={toneForStatus(vehicle.verification_status)}>
                {vehicle.verification_status}
              </Pill>
            </div>
            <div>
              <div className={styles.summaryLabel}>Operational</div>
              <Pill tone={toneForStatus(vehicle.operational_status)}>
                {vehicle.operational_status}
              </Pill>
            </div>
            {canApproveOrReject && (
              <div className={styles.summaryActions}>
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={isWorking}
                  onClick={() =>
                    runAction("Vehicle approved.", () =>
                      approveVehicle(vehicleId),
                    )
                  }
                >
                  Approve
                </button>
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isWorking}
                  onClick={() => setShowRejectField((v) => !v)}
                >
                  Reject
                </button>
              </div>
            )}
          </div>

          {showRejectField && (
            <div className={styles.reasonRow}>
              <input
                type="text"
                placeholder="Reason (optional)"
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                className={styles.reasonInput}
                aria-label="Rejection reason"
              />
              <button
                type="button"
                className={styles.dangerButton}
                disabled={isWorking}
                onClick={() =>
                  runAction("Vehicle rejected.", () =>
                    rejectVehicle(vehicleId, rejectReason),
                  )
                }
              >
                Confirm reject
              </button>
            </div>
          )}

          {actionError && (
            <div className={styles.errorBanner} role="alert">
              {actionError}
            </div>
          )}
          {actionSuccess && (
            <div className={styles.successBanner} role="status">
              {actionSuccess}
            </div>
          )}

          <div className={styles.sectionLabel}>Documents</div>
          <div className={styles.panel}>
            {documentsLoading && (
              <p className={styles.emptyState}>Loading documents…</p>
            )}
            {!documentsLoading && documentsError && (
              <div className={styles.errorBanner} role="alert">
                {documentsError}
              </div>
            )}
            {!documentsLoading && !documentsError && documents && (
              documents.length === 0 ? (
                <p className={styles.emptyState}>No documents submitted yet.</p>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Number</th>
                      <th>Status</th>
                      <th>Expires</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr key={doc.document_id}>
                        <td>{doc.document_type}</td>
                        <td>{doc.document_number}</td>
                        <td>
                          <Pill tone={toneForStatus(doc.verification_status)}>
                            {doc.verification_status}
                          </Pill>
                        </td>
                        <td>
                          {doc.expires_at
                            ? new Date(doc.expires_at).toLocaleDateString("en-IN")
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
