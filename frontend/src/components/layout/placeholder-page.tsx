import { PageHeading } from "@/components/ui/typography";
import { Surface } from "@/components/ui/surface";

// Deliberately no fake records, status, counts or enabled business actions.
export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="max-w-[760px]">
      <PageHeading title={title} />
      <Surface>
        <p className="text-sm text-secondary">{description}</p>
      </Surface>
    </div>
  );
}
