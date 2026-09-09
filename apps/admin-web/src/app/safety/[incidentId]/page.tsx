import { IncidentDetailPage } from "@/components/safety/IncidentDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ incidentId: string }>;
}) {
  const { incidentId } = await params;
  return <IncidentDetailPage incidentId={incidentId} />;
}
