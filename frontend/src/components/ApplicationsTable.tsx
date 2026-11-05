import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import type { KeyboardEvent, ReactNode } from "react";
import type { Application } from "../api/client";
import { formatDate, parseDate } from "../format";
import { StatusBadge } from "./StatusBadge";

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
    cell: (info) => {
      const value = info.getValue();
      return value ? (
        <span className="cell-date">{formatDate(value)}</span>
      ) : (
        <span className="cell-empty">Not set</span>
      );
    },
  }),
  columnHelper.accessor("updated_at", {
    header: "Last Updated",
    id: "updated_at",
    cell: (info) => <span className="cell-date">{formatDate(info.getValue())}</span>,
  }),
];

/* Week bucket for the group separators shown when sorting by a date column. */
function weekLabel(value: string | null): string {
  if (!value) return "No date";
  const date = parseDate(value);
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
  hasFilters: boolean;
  onClearFilters: () => void;
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
        <tr key={i} className="skeleton-row">
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
  hasFilters,
  onClearFilters,
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

  const handleRowKeyDown = (event: KeyboardEvent, application: Application) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowClick(application);
    }
  };

  if (!loading && applications.length === 0) {
    return (
      <div className="table-card">
        {hasFilters ? (
          <div className="empty-state">
            <h2>No matches</h2>
            <p>No applications match this search or status filter.</p>
            <button type="button" className="btn btn--ghost" onClick={onClearFilters}>
              Clear filters
            </button>
          </div>
        ) : (
          <div className="empty-state">
            <h2>No applications yet</h2>
            <p>Press Sync now to scan the last 90 days of Gmail for job applications.</p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="table-card">
      <div className="table-scroll">
        <table
          className={`app-table${loading && !initialLoad ? " app-table--busy" : ""}`}
          aria-busy={loading}
        >
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const active = sortColumn === header.column.id;
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={active ? (sortDescending ? "descending" : "ascending") : "none"}
                    >
                      <button
                        type="button"
                        className="th-sort"
                        onClick={() => handleHeaderClick(header.column.id)}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <span className="sort-arrow" aria-hidden="true">
                          {active ? (sortDescending ? "↓" : "↑") : ""}
                        </span>
                      </button>
                    </th>
                  );
                })}
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
                          <th colSpan={columns.length} scope="colgroup">
                            {label}
                          </th>
                        </tr>,
                      );
                      previousLabel = label;
                    }
                  }
                  rows.push(
                    <tr
                      key={row.id}
                      className="data-row"
                      tabIndex={0}
                      aria-label={`Edit ${row.original.company}${
                        row.original.job_title ? `, ${row.original.job_title}` : ""
                      }`}
                      onClick={() => onRowClick(row.original)}
                      onKeyDown={(e) => handleRowKeyDown(e, row.original)}
                    >
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
