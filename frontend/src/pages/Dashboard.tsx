import { useCallback, useEffect, useState } from "react";
import type { Application, ApplicationStatus, User } from "../api/client";
import { api } from "../api/client";
import { ApplicationDetailDrawer } from "../components/ApplicationDetailDrawer";
import { ApplicationsTable } from "../components/ApplicationsTable";
import { SyncButton } from "../components/SyncButton";

const STATUS_FILTER_OPTIONS: (ApplicationStatus | "")[] = [
  "",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
  "unknown",
];

const PAGE_SIZE = 25;

interface DashboardProps {
  user: User;
  onLoggedOut: () => void;
}

export function Dashboard({ user, onLoggedOut }: DashboardProps) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "">("");
  const [sort, setSort] = useState("-updated_at");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Application | null>(null);

  const fetchApplications = useCallback(() => {
    setLoading(true);
    api
      .listApplications({ search, status: statusFilter, sort, page, page_size: PAGE_SIZE })
      .then((result) => {
        setApplications(result.items);
        setTotal(result.total);
      })
      .finally(() => setLoading(false));
  }, [search, statusFilter, sort, page]);

  useEffect(() => {
    fetchApplications();
  }, [fetchApplications]);

  const handleLogout = async () => {
    await api.logout();
    onLoggedOut();
  };

  return (
    <div style={{ padding: "2rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Application Tracker</h1>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span>{user.name ?? user.email}</span>
          <button type="button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1.5rem" }}>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <input
            type="text"
            placeholder="Search company or job title..."
            value={search}
            onChange={(e) => {
              setPage(1);
              setSearch(e.target.value);
            }}
          />
          <select
            value={statusFilter}
            onChange={(e) => {
              setPage(1);
              setStatusFilter(e.target.value as ApplicationStatus | "");
            }}
          >
            {STATUS_FILTER_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option === "" ? "All statuses" : option}
              </option>
            ))}
          </select>
        </div>
        <SyncButton onSyncComplete={fetchApplications} />
      </div>

      <ApplicationsTable
        applications={applications}
        total={total}
        page={page}
        pageSize={PAGE_SIZE}
        sort={sort}
        loading={loading}
        onSortChange={(newSort) => {
          setPage(1);
          setSort(newSort);
        }}
        onPageChange={setPage}
        onRowClick={setSelected}
      />

      {selected && (
        <ApplicationDetailDrawer
          application={selected}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            fetchApplications();
          }}
          onDeleted={() => {
            setSelected(null);
            fetchApplications();
          }}
        />
      )}
    </div>
  );
}
