import { GpsDisputeDetailPage } from "@/components/support/GpsDisputeDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ disputeId: string }>;
}) {
  const { disputeId } = await params;
  return <GpsDisputeDetailPage disputeId={disputeId} />;
}
