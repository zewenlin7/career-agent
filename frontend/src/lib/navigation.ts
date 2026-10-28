export type NavigationItem = { href: string; label: string; exact?: boolean };

export function isActivePath(pathname: string, item: NavigationItem): boolean {
  return pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`));
}

export const productNavigation: NavigationItem[] = [
  { href: "/applications", label: "申请" },
  { href: "/profile", label: "个人资料" },
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
    { href: `${root}/summary`, label: "概览" },
    { href: `${root}/research-fit`, label: "研究与匹配" },
    { href: `${root}/apply`, label: "投递材料" },
    { href: `${root}/interview`, label: "面试" },
    { href: `${root}/review`, label: "复盘" },
  ];
}
export const applicationSections = {
  apply: [
    ["resume", "简历"],
    ["greeting", "招呼语"],
    ["submissions", "投递记录"],
  ],
  interview: [
    ["preparation", "面试准备"],
    ["mock", "模拟面试"],
    ["actual", "记录真实面试"],
    ["history", "历史面试"],
  ],
  review: [
    ["debriefs", "面试复盘"],
    ["knowledge-notes", "求职笔记"],
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
