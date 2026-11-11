"use client";
import { useEffect, useRef, type ReactNode } from "react";

/** Exact-link arrival only: wait for data, then follow layout until user interaction. */
export function ResultDestination({
  identity,
  requested,
  ready = true,
  children,
  anchor,
}: {
  identity: string;
  requested: string | null;
  ready?: boolean;
  children: ReactNode;
  anchor?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const visited = useRef<string | null>(null);
  useEffect(() => {
    if (!ready || !requested || requested !== identity || visited.current === requested) return;
    let active = true;
    let frame = 0;
    const align = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!active || !ref.current) return;
        const target =
          (anchor ? ref.current.querySelector<HTMLElement>(anchor) : null) || ref.current;
        const top = target.getBoundingClientRect().top;
        if (Math.abs(top - 24) > 2) window.scrollBy({ top: top - 24, behavior: "instant" });
        // Mark only after a rendered, identity-matched destination was actually positioned.
        visited.current = requested;
      });
    };
    const stop = () => {
      active = false;
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
    const observer = new ResizeObserver(align);
    observer.observe(document.body);
    align();
    void document.fonts.ready.then(() => {
      if (active) align();
    });
    window.addEventListener("wheel", stop, { passive: true });
    window.addEventListener("touchstart", stop, { passive: true });
    window.addEventListener("pointerdown", stop);
    window.addEventListener("keydown", stop);
    return () => {
      stop();
      window.removeEventListener("wheel", stop);
      window.removeEventListener("touchstart", stop);
      window.removeEventListener("pointerdown", stop);
      window.removeEventListener("keydown", stop);
    };
  }, [identity, requested, ready, anchor]);
  return (
    <div ref={ref} data-result-destination={identity} className="scroll-mt-6">
      {children}
    </div>
  );
}
