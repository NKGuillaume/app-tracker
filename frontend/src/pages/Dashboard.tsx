import { useCallback, useEffect, useRef, useState } from "react";
import type { Application, ApplicationStatus, User } from "../api/client";
import { api } from "../api/client";
import { ApplicationDetailDrawer } from "../components/ApplicationDetailDrawer";
import { ApplicationsTable } from "../components/ApplicationsTable";
import { SyncButton } from "../components/SyncButton";
import { capitalize } from "../format";

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
const SEARCH_DEBOUNCE_MS = 300;

interface DashboardProps {
  user: User;
  onLoggedOut: () => void;
}

export function Dashboard({ user, onLoggedOut }: DashboardProps) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "">("");
  const [sort, setSort] = useState("-application_date");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Application | null>(null);
  const requestId = useRef(0);

  // Debounce typing so each keystroke doesn't hit the API.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const fetchApplications = useCallback(() => {
    // Only the latest request may write state, so a slow earlier response
    // can't overwrite newer results.
    const id = ++requestId.current;
    setLoading(true);
    setLoadError(false);
    api
      .listApplications({ search, status: statusFilter, sort, page, page_size: PAGE_SIZE })
      .then((result) => {
        if (id !== requestId.current) return;
        // Deleting the last row on the final page would otherwise strand the
        // user on an empty page.
        const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE));
        if (page > lastPage) {
          setPage(lastPage);
          return;
        }
        setApplications(result.items);
        setTotal(result.total);
      })
      .catch(() => {
        if (id === requestId.current) setLoadError(true);
      })
      .finally(() => {
        if (id === requestId.current) setLoading(false);
      });
  }, [search, statusFilter, sort, page]);

  useEffect(() => {
    fetchApplications();
  }, [fetchApplications]);

  const handleLogout = async () => {
    await api.logout().catch(() => undefined);
    onLoggedOut();
  };

  const hasFilters = search !== "" || statusFilter !== "";

  const clearFilters = () => {
    setSearchInput("");
    setSearch("");
    setStatusFilter("");
    setPage(1);
  };

  return (
    <div className="page">
      <header className="app-header">
        <h1>Application Tracker</h1>
        <div className="app-header__user">
          <span className="app-header__name">{user.name ?? user.email}</span>
          <button type="button" className="btn btn--ghost" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <div className="toolbar">
        <div className="toolbar__filters">
          <input
            type="search"
            className="input"
            placeholder="Search company or job title"
            aria-label="Search company or job title"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <select
            className="select"
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => {
              setPage(1);
              setStatusFilter(e.target.value as ApplicationStatus | "");
            }}
          >
            {STATUS_FILTER_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option === "" ? "All statuses" : capitalize(option)}
              </option>
            ))}
          </select>
        </div>
        <SyncButton onSyncComplete={fetchApplications} />
      </div>

      {loadError ? (
        <div className="table-card">
          <div className="empty-state" role="alert">
            <h2>Couldn&apos;t load applications</h2>
            <p>Something went wrong talking to the server.</p>
            <button type="button" className="btn btn--ghost" onClick={fetchApplications}>
              Try again
            </button>
          </div>
        </div>
      ) : (
        <ApplicationsTable
          applications={applications}
          total={total}
          page={page}
          pageSize={PAGE_SIZE}
          sort={sort}
          loading={loading}
          hasFilters={hasFilters}
          onClearFilters={clearFilters}
          onSortChange={(newSort) => {
            setPage(1);
            setSort(newSort);
          }}
          onPageChange={setPage}
          onRowClick={setSelected}
        />
      )}

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
