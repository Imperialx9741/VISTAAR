import { RideDetailPage } from "@/components/rides/RideDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ rideId: string }>;
}) {
  const { rideId } = await params;
  return <RideDetailPage rideId={rideId} />;
}
