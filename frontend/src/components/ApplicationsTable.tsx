import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import type { Application, ApplicationStatus } from "../api/client";

const STATUS_COLORS: Record<ApplicationStatus, string> = {
  applied: "#5b6cf0",
  interview: "#c98a1f",
  offer: "#1f9d55",
  rejected: "#d1453b",
  withdrawn: "#6b7280",
  unknown: "#9ca3af",
};

function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.15rem 0.6rem",
        borderRadius: "999px",
        fontSize: "0.8rem",
        color: "white",
        backgroundColor: STATUS_COLORS[status],
        textTransform: "capitalize",
      }}
    >
      {status}
    </span>
  );
}

const columnHelper = createColumnHelper<Application>();

const columns = [
  columnHelper.accessor("company", { header: "Company", id: "company" }),
  columnHelper.accessor("job_title", {
    header: "Job Title",
    id: "job_title",
    cell: (info) => info.getValue() ?? "—",
  }),
  columnHelper.accessor("status", {
    header: "Status",
    id: "status",
    cell: (info) => <StatusBadge status={info.getValue()} />,
  }),
  columnHelper.accessor("application_date", {
    header: "Application Date",
    id: "application_date",
    cell: (info) => info.getValue() ?? "—",
  }),
  columnHelper.accessor("updated_at", {
    header: "Last Updated",
    id: "updated_at",
    cell: (info) => new Date(info.getValue()).toLocaleDateString(),
  }),
];

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

  const handleHeaderClick = (columnId: string) => {
    if (columnId === sortColumn) {
      onSortChange(sortDescending ? columnId : `-${columnId}`);
    } else {
      onSortChange(`-${columnId}`);
    }
  };

  if (!loading && applications.length === 0) {
    return (
      <p style={{ color: "#666", marginTop: "1.5rem" }}>
        No applications yet. Click &quot;Sync now&quot; to scan your Gmail for job
        applications.
      </p>
    );
  }

  return (
    <div style={{ marginTop: "1.5rem" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  onClick={() => handleHeaderClick(header.column.id)}
                  style={{
                    textAlign: "left",
                    padding: "0.5rem",
                    borderBottom: "2px solid #e5e7eb",
                    cursor: "pointer",
                    userSelect: "none",
                  }}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {sortColumn === header.column.id ? (sortDescending ? " ↓" : " ↑") : ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => onRowClick(row.original)}
              style={{ cursor: "pointer", opacity: loading ? 0.5 : 1 }}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} style={{ padding: "0.5rem", borderBottom: "1px solid #f0f0f0" }}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1rem" }}>
        <span style={{ color: "#666", fontSize: "0.9rem" }}>
          {total} application{total === 1 ? "" : "s"}
        </span>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button type="button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
