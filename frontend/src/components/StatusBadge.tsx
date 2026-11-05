import type { ApplicationStatus } from "../api/client";

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return <span className={`badge badge--${status}`}>{status}</span>;
}
