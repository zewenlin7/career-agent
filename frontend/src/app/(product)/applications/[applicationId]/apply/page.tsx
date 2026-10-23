import { redirect } from "next/navigation";
export default async function Page({ params }: { params: Promise<{ applicationId: string }> }) {
  const { applicationId } = await params;
  redirect(`/applications/${encodeURIComponent(applicationId)}/apply/resume`);
}
