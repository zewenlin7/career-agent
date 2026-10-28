"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
export function ProfileNavigation() {
  const path = usePathname();
  return (
    <nav aria-label="资料与简历" className="mb-8 flex gap-6 border-b border-line">
      {[
        ["/profile", "个人资料"],
        ["/profile/resumes", "简历库"],
      ].map(([href, label]) => (
        <Link
          key={href}
          href={href}
          aria-current={path === href ? "page" : undefined}
          className={`min-h-11 border-b-2 py-3 text-sm ${path === href ? "border-accent text-accent-ink" : "border-transparent text-secondary"}`}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
