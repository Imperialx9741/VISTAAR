import { CampaignDetailPage } from "@/components/advertisements/CampaignDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  return <CampaignDetailPage campaignId={campaignId} />;
}
