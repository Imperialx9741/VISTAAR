import { CaseDetailPage } from "@/components/support/CaseDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <CaseDetailPage caseId={caseId} />;
}
