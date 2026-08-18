import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import type { ReactNode } from "react";
import type { Application, ApplicationStatus } from "../api/client";

function StatusBadge({ status }: { status: ApplicationStatus }) {
  return <span className={`badge badge--${status}`}>{status}</span>;
}

const columnHelper = createColumnHelper<Application>();

const columns = [
  columnHelper.accessor("company", {
    header: "Company",
    id: "company",
    cell: (info) => <span className="cell-company">{info.getValue()}</span>,
  }),
  columnHelper.accessor("job_title", {
    header: "Job Title",
    id: "job_title",
    cell: (info) => info.getValue() ?? <span className="cell-empty">Not set</span>,
  }),
  columnHelper.accessor("status", {
    header: "Status",
    id: "status",
    cell: (info) => <StatusBadge status={info.getValue()} />,
  }),
  columnHelper.accessor("application_date", {
    header: "Applied",
    id: "application_date",
    cell: (info) =>
      info.getValue() ? (
        <span className="cell-date">{info.getValue()}</span>
      ) : (
        <span className="cell-empty">Not set</span>
      ),
  }),
  columnHelper.accessor("updated_at", {
    header: "Last Updated",
    id: "updated_at",
    cell: (info) => (
      <span className="cell-date">{new Date(info.getValue()).toLocaleDateString()}</span>
    ),
  }),
];

/* Week bucket for the group separators shown when sorting by a date column.
   Date-only strings ("2026-08-01") are parsed as local dates on purpose:
   new Date("2026-08-01") would read as UTC midnight and can land in the wrong
   day (and week) in western timezones. */
function weekLabel(value: string | null): string {
  if (!value) return "No date";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.round((startOfToday.getTime() - startOfDay.getTime()) / 86_400_000);
  if (days < 7) return "This week";
  if (days < 14) return "Last week";
  return `${Math.floor(days / 7)} weeks ago`;
}

const GROUPABLE_COLUMNS = ["application_date", "updated_at"] as const;
type GroupableColumn = (typeof GROUPABLE_COLUMNS)[number];

interface ApplicationsTableProps {
  applications: Application[];
  total: number;
  page: number;
  pageSize: number;
  sort: string;
  loading: boolean;
  onSortChange: (sort: string) => void;
  onPageChange: (page: number) => void;
  onRowClick: (application: Application) => void;
}

/* Skeleton rows mirror the real column layout so the table doesn't jump
   when data arrives. */
function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 6 }, (_, i) => (
        <tr key={i} style={{ cursor: "default" }}>
          {columns.map((_, j) => (
            <td key={j}>
              <span className="skeleton" style={{ width: j === 0 ? "70%" : "50%" }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function ApplicationsTable({
  applications,
  total,
  page,
  pageSize,
  sort,
  loading,
  onSortChange,
  onPageChange,
  onRowClick,
}: ApplicationsTableProps) {
  const table = useReactTable({
    data: applications,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const sortColumn = sort.startsWith("-") ? sort.slice(1) : sort;
  const sortDescending = sort.startsWith("-");
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const initialLoad = loading && applications.length === 0;

  const handleHeaderClick = (columnId: string) => {
    if (columnId === sortColumn) {
      onSortChange(sortDescending ? columnId : `-${columnId}`);
    } else {
      onSortChange(`-${columnId}`);
    }
  };

  if (!loading && applications.length === 0) {
    return (
      <div className="table-card">
        <div className="empty-state">
          <h2>No applications yet</h2>
          <p>
            Click &quot;Sync now&quot; to scan your Gmail for job applications, or adjust
            your search and filters.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="table-card">
      <div className="table-scroll">
        <table className={`app-table${loading && !initialLoad ? " app-table--busy" : ""}`}>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    onClick={() => handleHeaderClick(header.column.id)}
                    aria-sort={
                      sortColumn === header.column.id
                        ? sortDescending
                          ? "descending"
                          : "ascending"
                        : undefined
                    }
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {sortColumn === header.column.id && (
                      <span className="sort-arrow">{sortDescending ? "↓" : "↑"}</span>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {initialLoad ? (
              <SkeletonRows />
            ) : (
              (() => {
                const groupColumn = GROUPABLE_COLUMNS.find((c) => c === sortColumn);
                const rows: ReactNode[] = [];
                let previousLabel: string | null = null;

                for (const row of table.getRowModel().rows) {
                  if (groupColumn) {
                    const label = weekLabel(row.original[groupColumn as GroupableColumn]);
                    if (label !== previousLabel) {
                      rows.push(
                        <tr key={`week-${label}`} className="week-row">
                          <td colSpan={columns.length}>{label}</td>
                        </tr>,
                      );
                      previousLabel = label;
                    }
                  }
                  rows.push(
                    <tr key={row.id} onClick={() => onRowClick(row.original)}>
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>,
                  );
                }
                return rows;
              })()
            )}
          </tbody>
        </table>
      </div>

      <div className="table-footer">
        <span>
          {total} application{total === 1 ? "" : "s"}
        </span>
        <div className="table-footer__pager">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
