export type NavigationItem = { href: string; label: string; exact?: boolean };

export function isActivePath(pathname: string, item: NavigationItem): boolean {
  return pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`));
}

export const productNavigation: NavigationItem[] = [
  { href: "/applications", label: "Applications" },
  { href: "/profile", label: "Profile" },
];
export const internalNavigation: NavigationItem[] = [
  { href: "/internal/operations", label: "Operations" },
  { href: "/internal/evaluation", label: "Evaluation" },
];
export const operationsNavigation: NavigationItem[] = [
  { href: "/internal/operations/overview", label: "Overview" },
  { href: "/internal/operations/runs", label: "Runs" },
  { href: "/internal/operations/incidents", label: "Incidents & Recovery" },
  { href: "/internal/operations/controls", label: "Controls" },
];
export const evaluationNavigation: NavigationItem[] = [
  { href: "/internal/evaluation/production-quality", label: "Production Quality" },
  { href: "/internal/evaluation/test-runs", label: "Test Runs" },
  { href: "/internal/evaluation/comparisons", label: "Comparisons" },
  { href: "/internal/evaluation/calibration-triage", label: "Calibration & Triage" },
];
export function applicationNavigation(id: string): NavigationItem[] {
  const root = `/applications/${encodeURIComponent(id)}`;
  return [
    { href: `${root}/summary`, label: "Summary" },
    { href: `${root}/research-fit`, label: "Research & Fit" },
    { href: `${root}/apply`, label: "Apply" },
    { href: `${root}/interview`, label: "Interview" },
    { href: `${root}/review`, label: "Review" },
  ];
}
export const applicationSections = {
  apply: [
    ["resume", "Resume"],
    ["greeting", "Greeting"],
    ["submissions", "Submissions"],
  ],
  interview: [
    ["preparation", "Interview Prep"],
    ["mock", "Mock Interview"],
    ["actual", "Record Actual Interview"],
    ["history", "Previous Interviews"],
  ],
  review: [
    ["debriefs", "Debriefs"],
    ["knowledge-notes", "Knowledge Notes"],
  ],
} as const;

export function sectionNavigation(
  id: string,
  section: keyof typeof applicationSections,
): NavigationItem[] {
  return applicationSections[section].map(([path, label]) => ({
    href: `/applications/${encodeURIComponent(id)}/${section}/${path}`,
    label,
  }));
}
