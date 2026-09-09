import { DriverBonusRuleDetailPage } from "@/components/referrals/DriverBonusRuleDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ ruleId: string }>;
}) {
  const { ruleId } = await params;
  return <DriverBonusRuleDetailPage ruleId={ruleId} />;
}
