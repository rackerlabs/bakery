import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";

type OperatorTableProps<TData extends object> = {
  data: TData[];
  columns: ColumnDef<TData>[];
  getRowId: (row: TData) => string;
  selectedRowId?: string | null;
  onSelectRow?: (row: TData) => void;
  emptyState?: ReactNode;
};

export function OperatorTable<TData extends object>({
  data,
  columns,
  getRowId,
  selectedRowId,
  onSelectRow,
  emptyState,
}: OperatorTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId,
  });

  const rows = useMemo(() => table.getRowModel().rows, [table]);

  if (rows.length === 0) {
    return <div className="empty-state">{emptyState ?? "No matching records."}</div>;
  }

  return (
    <div className="table-shell">
      <table className="operator-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id}>
                  {header.isPlaceholder ? null : (
                    <button
                      className="table-heading-button"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </button>
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {rows.map((row) => {
            const rowId = getRowId(row.original);
            return (
              <tr
                key={row.id}
                className={selectedRowId === rowId ? "is-selected" : undefined}
                onClick={() => onSelectRow?.(row.original)}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
