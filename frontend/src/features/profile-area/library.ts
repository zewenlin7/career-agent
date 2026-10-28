import { api, ApiError } from "../workspace/client";
import type { Draft } from "./contracts";

export async function savedResumes(_path: string, signal: AbortSignal): Promise<Draft[]> {
  const items: Draft[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api<Draft[]>(
      `resume-workspaces?limit=100&offset=${offset}`,
      "GET",
      undefined,
      signal,
    );
    items.push(...page);
    if (page.length < 100) return items;
  }
}

export type ResumeChoice = {
  id: string;
  name: string;
  profile_id: string;
  workspace?: boolean;
  revision: number;
};
export async function resumeChoices(
  _path: string,
  signal: AbortSignal,
): Promise<{ items: ResumeChoice[] }> {
  const drafts = await savedResumes("", signal);
  const items: ResumeChoice[] = drafts
    .filter((d) => !d.accepted_revision_id && d.profile_id)
    .map((d) => ({
      id: d.id,
      name: d.name,
      profile_id: d.profile_id!,
      revision: d.revision,
      workspace: true,
    }));
  for (let offset = 0; ; offset += 100) {
    const page = await api<{ items: ResumeChoice[]; has_more: boolean }>(
      `resume-library/versions?limit=100&offset=${offset}`,
      "GET",
      undefined,
      signal,
    );
    items.push(...page.items);
    if (!page.has_more) return { items };
  }
}
export async function resolveResume(
  choice: ResumeChoice,
): Promise<{ id: string; profile_id: string }> {
  if (!choice.workspace) return choice;
  const result = await api<{
    resume_revision_id: string | null;
    profile_id: string;
    claim_issues: unknown[];
  }>(`resume-workspaces/${choice.id}/resolve`, "POST", { expected_revision: choice.revision });
  if (!result.resume_revision_id) throw new ApiError("resume_claims_unsupported");
  return { id: result.resume_revision_id, profile_id: result.profile_id };
}
