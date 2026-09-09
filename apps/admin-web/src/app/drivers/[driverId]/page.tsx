import { DriverDetailPage } from "@/components/people/DriverDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ driverId: string }>;
}) {
  const { driverId } = await params;
  return <DriverDetailPage driverId={driverId} />;
}
