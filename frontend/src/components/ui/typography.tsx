import type { ReactNode } from "react";

export function PageHeading({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-7 max-w-[760px]">
      <h1 className="font-serif text-[21px] leading-relaxed font-semibold tracking-[-0.3px]">
        {title}
      </h1>
      {description && <p className="mt-2 text-sm text-secondary">{description}</p>}
    </div>
  );
}
export function SectionHeading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="text-base leading-relaxed font-semibold">
      {children}
    </h2>
  );
}
