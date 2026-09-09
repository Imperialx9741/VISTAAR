import { VehicleDetailPage } from "@/components/people/VehicleDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ vehicleId: string }>;
}) {
  const { vehicleId } = await params;
  return <VehicleDetailPage vehicleId={vehicleId} />;
}
