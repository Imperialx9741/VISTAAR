import { BroadcastDetailPage } from "@/components/notifications/BroadcastDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ broadcastId: string }>;
}) {
  const { broadcastId } = await params;
  return <BroadcastDetailPage broadcastId={broadcastId} />;
}
