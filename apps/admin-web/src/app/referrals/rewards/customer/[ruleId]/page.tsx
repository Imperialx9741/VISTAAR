import { CustomerRewardRuleDetailPage } from "@/components/referrals/CustomerRewardRuleDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ ruleId: string }>;
}) {
  const { ruleId } = await params;
  return <CustomerRewardRuleDetailPage ruleId={ruleId} />;
}
