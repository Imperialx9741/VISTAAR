import { TemplateDetailPage } from "@/components/notifications/TemplateDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ templateId: string }>;
}) {
  const { templateId } = await params;
  return <TemplateDetailPage templateId={templateId} />;
}
