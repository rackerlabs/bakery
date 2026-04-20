import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it, vi } from "vitest";

import { OperatorTable } from "./OperatorTable";

type Row = {
  id: string;
  monitor: string;
  status: string;
};

const columns: ColumnDef<Row>[] = [
  { header: "Monitor", accessorKey: "monitor" },
  { header: "Status", accessorKey: "status" },
];

describe("OperatorTable", () => {
  it("updates rendered rows when the backing data changes", async () => {
    const user = userEvent.setup();
    const onSelectRow = vi.fn();
    const initialRows: Row[] = [{ id: "1", monitor: "monitor-a", status: "unreachable" }];
    const refreshedRows: Row[] = [{ id: "1", monitor: "monitor-a", status: "healthy" }];

    const { rerender } = render(
      <OperatorTable
        data={initialRows}
        columns={columns}
        getRowId={(row) => row.id}
        selectedRowId="1"
        onSelectRow={onSelectRow}
      />,
    );

    expect(screen.getByText("unreachable")).toBeInTheDocument();

    rerender(
      <OperatorTable
        data={refreshedRows}
        columns={columns}
        getRowId={(row) => row.id}
        selectedRowId="1"
        onSelectRow={onSelectRow}
      />,
    );

    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.queryByText("unreachable")).not.toBeInTheDocument();

    await user.click(screen.getByRole("cell", { name: "healthy" }));
    expect(onSelectRow).toHaveBeenCalledWith(refreshedRows[0]);
  });
});
