import { AssignmentDetailPage } from "@/components/advertisements/AssignmentDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = await params;
  return <AssignmentDetailPage assignmentId={assignmentId} />;
}
