import { getApplicationContext } from "@/features/applications/server";
import { PageHeading } from "@/components/ui/typography";
import { ReadProblem } from "@/components/product/read-state";
import { ResearchFit } from "./research";
import { PreparationPage } from "./preparation";
import { ResumePage, SubmissionsPage } from "./materials";
import { ActualPage, MockPage, HistoryPage } from "./interviews";
import { DebriefsPage, KnowledgePage } from "./review";
const titles = {
  research: "Research & Fit",
  resume: "Resume",
  greeting: "Greeting",
  submissions: "Submissions",
  preparation: "Interview Prep",
  mock: "Mock Interview",
  actual: "Record Actual Interview",
  history: "Previous Interviews",
  debriefs: "Debriefs",
  notes: "Knowledge Notes",
};
export type WorkspaceFeature = keyof typeof titles;
export async function WorkspaceEntry({ id, feature }: { id: string; feature: WorkspaceFeature }) {
  let ctx;
  try {
    ctx = await getApplicationContext(id);
  } catch {
    return <ReadProblem href={`/applications/${id}/summary`} />;
  }
  const page = {
    research: <ResearchFit ctx={ctx} />,
    resume: <ResumePage ctx={ctx} />,
    greeting: <PreparationPage ctx={ctx} target="greeting_generation" />,
    submissions: <SubmissionsPage ctx={ctx} />,
    preparation: <PreparationPage ctx={ctx} target="interview_preparation" />,
    mock: <MockPage ctx={ctx} />,
    actual: <ActualPage ctx={ctx} />,
    history: <HistoryPage ctx={ctx} />,
    debriefs: <DebriefsPage ctx={ctx} />,
    notes: <KnowledgePage ctx={ctx} />,
  }[feature];
  return (
    <>
      <PageHeading title={titles[feature]} />
      {page}
    </>
  );
}
