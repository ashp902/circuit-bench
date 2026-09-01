import type { ReactNode } from "react";

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <section className="empty-state" aria-label={title}><div><h2>{title}</h2><p>{children}</p></div>{action && <div className="empty-state__action">{action}</div>}</section>;
}
