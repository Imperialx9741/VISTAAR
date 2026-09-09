import { AdminDetailPage } from "@/components/admin-management/AdminDetailPage";

// Next 16: dynamic segment params are a Promise now (see AGENTS.md at
// the app root — breaking change from earlier Next versions). This page
// stays a thin async Server Component, same shape as every other
// page.tsx in this app, just awaiting params before handing a plain
// string down to the Client Component that does the real work.
export default async function Page({
  params,
}: {
  params: Promise<{ adminId: string }>;
}) {
  const { adminId } = await params;
  return <AdminDetailPage adminId={adminId} />;
}
