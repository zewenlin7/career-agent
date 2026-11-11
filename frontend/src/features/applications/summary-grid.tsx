"use client";
import { Children, useLayoutEffect, useRef, type ReactNode } from "react";

/** Row-major DOM; paired read heights, independent column flow while editing. */
export function SummaryGrid({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const grid = root.current!;
    const cells = Array.from(grid.children) as HTMLElement[];
    let baseline: number[] = [];
    const layout = () => {
      const editing = cells.map((cell) => !!cell.querySelector('[data-summary-editing="true"]'));
      const natural = cells.map((cell) => {
        if (cell.querySelector('[data-summary-fixed="true"]')) return 430;
        const title = cell.querySelector<HTMLElement>(".summary-title")!;
        const body = cell.querySelector<HTMLElement>("[data-summary-content]")!;
        const action = cell.querySelector<HTMLElement>("[data-summary-action]");
        const style = getComputedStyle(cell.querySelector(".summary-card")!);
        const titleStyle = getComputedStyle(title);
        return Math.ceil(
          parseFloat(style.paddingTop) +
            parseFloat(style.paddingBottom) +
            parseFloat(style.borderTopWidth) +
            parseFloat(style.borderBottomWidth) +
            title.getBoundingClientRect().height +
            parseFloat(titleStyle.marginBottom) +
            body.getBoundingClientRect().height +
            (action
              ? action.getBoundingClientRect().height +
                parseFloat(getComputedStyle(action).marginTop)
              : 0),
        );
      });
      if (!editing.some(Boolean) || !baseline.length) {
        baseline = natural.map((height, i) =>
          Math.max(height, natural[i % 2 ? i - 1 : i + 1] || 0),
        );
      }
      const next = [1, 1];
      cells.forEach((cell, i) => {
        const height = editing[i] ? Math.max(baseline[i], natural[i]) : baseline[i];
        const span = height + (i < cells.length - 2 ? 20 : 0);
        cell.style.setProperty("--summary-row", String(next[i % 2]));
        cell.style.setProperty("--summary-span", String(span));
        next[i % 2] += span;
      });
      grid.classList.add("summary-measured");
    };
    const resize = new ResizeObserver(layout);
    grid
      .querySelectorAll("[data-summary-content], .summary-title, [data-summary-action]")
      .forEach((node) => resize.observe(node));
    const mutations = new MutationObserver(() => {
      grid.querySelectorAll("[data-summary-action]").forEach((node) => resize.observe(node));
      layout();
    });
    mutations.observe(grid, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["data-summary-editing"],
    });
    layout();
    return () => {
      resize.disconnect();
      mutations.disconnect();
    };
  }, []);
  return (
    <div ref={root} className="summary-grid">
      {Children.map(children, (child) => (
        <div className="summary-cell">{child}</div>
      ))}
    </div>
  );
}
