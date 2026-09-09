import { CustomerDetailPage } from "@/components/people/CustomerDetailPage";

export default async function Page({
  params,
}: {
  params: Promise<{ customerId: string }>;
}) {
  const { customerId } = await params;
  return <CustomerDetailPage customerId={customerId} />;
}
