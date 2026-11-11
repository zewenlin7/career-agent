import { ResumeLibrary } from "@/features/profile-area/resumes";
import { FrozenResume } from "@/features/profile-area/frozen-resume";
import { UUID_PATTERN } from "@/features/applications/contracts";
import { notFound } from "next/navigation";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ revision?: string; pdf?: string; workspace?: string }>;
}) {
  const query = await searchParams;
  if (query.revision) {
    if (!UUID_PATTERN.test(query.revision) || (query.pdf && !UUID_PATTERN.test(query.pdf)))
      notFound();
    return <FrozenResume revision={query.revision} pdf={query.pdf} />;
  }
  if (query.workspace && !UUID_PATTERN.test(query.workspace)) notFound();
  return <ResumeLibrary initialWorkspace={query.workspace} />;
}
