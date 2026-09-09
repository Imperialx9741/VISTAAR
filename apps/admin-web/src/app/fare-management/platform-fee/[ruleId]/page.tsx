import { PlatformFeeRuleDetailPage } from "@/components/fare-management/PlatformFeeRuleDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ ruleId: string }>;
}) {
  const { ruleId } = await params;
  return <PlatformFeeRuleDetailPage ruleId={ruleId} />;
}
