import { FareRuleDetailPage } from "@/components/fare-management/FareRuleDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ ruleId: string }>;
}) {
  const { ruleId } = await params;
  return <FareRuleDetailPage ruleId={ruleId} />;
}
