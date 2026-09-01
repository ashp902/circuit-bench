export function StatusIndicator({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <span className={`status-indicator status-indicator--${tone}`}><span aria-hidden />{children}</span>;
}
