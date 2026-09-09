import { DriverStrikeHistoryPage } from "@/components/people/DriverStrikeHistoryPage";

export default async function Page({
  params,
}: {
  params: Promise<{ driverId: string }>;
}) {
  const { driverId } = await params;
  return <DriverStrikeHistoryPage driverId={driverId} />;
}
