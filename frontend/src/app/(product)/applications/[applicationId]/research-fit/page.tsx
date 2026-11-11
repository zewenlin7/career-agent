import { redirect } from "next/navigation";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ applicationId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { applicationId } = await params,
    search = await searchParams;
  const section = search.research
    ? "company"
    : search.result || search.artifact
      ? "fit"
      : "description";
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(search))
    if (typeof value === "string") query.set(key, value);
  redirect(
    `/applications/${applicationId}/research-fit/${section}${query.size ? `?${query}` : ""}`,
  );
}
