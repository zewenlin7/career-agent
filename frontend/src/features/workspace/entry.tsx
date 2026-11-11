import { TargetBoundary } from "./target-boundary";
import { getApplicationContext } from "@/features/applications/server";
import { PageHeading } from "@/components/ui/typography";
import { ReadProblem } from "@/components/product/read-state";
import { ResearchFit, type ResearchSection } from "./research";
import { PreparationPage } from "./preparation";
import { ResumePage, SubmissionsPage } from "./materials";
import { ActualPage, MockPage, HistoryPage } from "./interviews";
import { DebriefsPage, KnowledgePage } from "./review";
const titles = {
  research: "研究与匹配",
  resume: "简历",
  greeting: "招呼语",
  submissions: "投递记录",
  preparation: "面试准备",
  mock: "模拟面试",
  actual: "记录真实面试",
  history: "历史面试",
  debriefs: "面试复盘",
  notes: "求职笔记",
};
export type WorkspaceFeature = keyof typeof titles;
export async function WorkspaceEntry({
  id,
  feature,
  researchSection = "description",
}: {
  id: string;
  feature: WorkspaceFeature;
  researchSection?: ResearchSection;
}) {
  let ctx;
  try {
    ctx = await getApplicationContext(id);
  } catch {
    return <ReadProblem href={`/applications/${id}/summary`} />;
  }
  const page = {
    research: <ResearchFit ctx={ctx} section={researchSection} />,
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
      {!["research", "resume", "greeting", "submissions", "preparation", "notes"].includes(
        feature,
      ) &&
        (["mock", "actual", "history", "debriefs"].includes(feature) ? (
          <h1 className="mb-7 text-2xl font-semibold">{titles[feature]}</h1>
        ) : (
          <PageHeading title={titles[feature]} />
        ))}
      <TargetBoundary
        preserveInputs={
          ["resume", "greeting", "preparation", "mock", "debriefs", "notes"].includes(feature) ||
          (feature === "research" && ["company", "fit"].includes(researchSection))
        }
      >
        {page}
      </TargetBoundary>
    </>
  );
}
