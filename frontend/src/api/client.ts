const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
}

export type ApplicationStatus =
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn"
  | "unknown";

export interface Application {
  id: string;
  company: string;
  job_title: string | null;
  application_date: string | null;
  status: ApplicationStatus;
  gmail_thread_id: string;
  raw_snippet: string | null;
  confidence: number | null;
  manually_edited: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedApplications {
  items: Application[];
  total: number;
  page: number;
  page_size: number;
}

export interface ListApplicationsParams {
  search?: string;
  status?: ApplicationStatus | "";
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface ApplicationUpdate {
  company?: string;
  job_title?: string | null;
  application_date?: string | null;
  status?: ApplicationStatus;
}

export interface SyncResult {
  status: string;
  scanned: number;
  skipped: number;
  new_applications: number;
  updated_applications: number;
  merged_duplicates?: number;
  heuristic_filtered?: number;
  llm_calls?: number;
  llm_rejected?: number;
  job_emails?: number;
  gmail_matched?: number;
  mailbox_90d_estimate?: number;
  duration_seconds?: number;
}

export interface SyncStatus {
  last_manual_sync_at: string | null;
}

function toQueryString(params: ListApplicationsParams): string {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.sort) query.set("sort", params.sort);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  const str = query.toString();
  return str ? `?${str}` : "";
}

export const api = {
  loginUrl: () => `${API_BASE_URL}/auth/login`,
  me: () => request<User>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  listApplications: (params: ListApplicationsParams) =>
    request<PaginatedApplications>(`/applications${toQueryString(params)}`),
  updateApplication: (id: string, patch: ApplicationUpdate) =>
    request<Application>(`/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteApplication: (id: string) =>
    request<void>(`/applications/${id}`, { method: "DELETE" }),

  syncManual: () => request<SyncResult>("/sync/manual", { method: "POST" }),
  syncStatus: () => request<SyncStatus>("/sync/status"),
};
