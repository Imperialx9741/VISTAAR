import { DriverWalletPage } from "@/components/finance/DriverWalletPage";

export default async function Page({
  params,
}: {
  params: Promise<{ driverId: string }>;
}) {
  const { driverId } = await params;
  return <DriverWalletPage driverId={driverId} />;
}
