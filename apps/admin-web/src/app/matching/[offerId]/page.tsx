import { OfferDetailPage } from "@/components/matching/OfferDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ offerId: string }>;
}) {
  const { offerId } = await params;
  return <OfferDetailPage offerId={offerId} />;
}
