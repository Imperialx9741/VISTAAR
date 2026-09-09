import { CampaignDetailPage } from "@/components/campaigns/CampaignDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  return <CampaignDetailPage campaignId={campaignId} />;
}
