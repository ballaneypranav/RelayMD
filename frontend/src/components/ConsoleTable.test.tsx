import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";

import { ConsoleTable } from "./ConsoleTable";

interface DemoRow {
  id: string;
  title: string;
  status: string;
  priority: string;
}

const rows: DemoRow[] = [
  { id: "gamma", title: "Gamma job", status: "failed", priority: "Low" },
  { id: "alpha", title: "Alpha job", status: "queued", priority: "High" },
  { id: "beta", title: "Beta job", status: "running", priority: "Medium" },
];

const columns: ColumnDef<DemoRow>[] = [
  {
    accessorKey: "title",
    header: "Title",
    cell: ({ row }) => <strong>{row.original.title}</strong>,
  },
  {
    accessorKey: "status",
    header: "Status",
  },
  {
    accessorKey: "priority",
    header: "Priority",
  },
];

function renderTable(overrides: Partial<Parameters<typeof ConsoleTable<DemoRow>>[0]> = {}) {
  return render(
    <ConsoleTable
      ariaLabel="Demo jobs"
      columns={columns}
      data={rows}
      emptyDescription="No demo rows match the current table state."
      emptyTitle="No demo rows"
      enableSelection
      getRowId={(row) => row.id}
      initialPageSize={2}
      renderExpandedRow={(row) => <div>Details for {row.original.title}</div>}
      searchPlaceholder="Search demo rows"
      {...overrides}
    />,
  );
}

describe("ConsoleTable", () => {
  it("filters, sorts, paginates, and toggles column visibility", async () => {
    const user = userEvent.setup();
    renderTable();

    const table = screen.getByRole("table", { name: "Demo jobs" });
    expect(within(table).getByText("Gamma job")).toBeInTheDocument();
    expect(within(table).getByText("Alpha job")).toBeInTheDocument();
    expect(within(table).queryByText("Beta job")).not.toBeInTheDocument();
    expect(screen.getByText("1-2 of 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(within(table).getByText("Beta job")).toBeInTheDocument();
    expect(screen.getByText("3-3 of 3")).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Search table" }), "alpha");
    expect(within(table).getByText("Alpha job")).toBeInTheDocument();
    expect(within(table).queryByText("Gamma job")).not.toBeInTheDocument();

    await user.clear(screen.getByRole("searchbox", { name: "Search table" }));
    await user.click(screen.getByRole("button", { name: /title/i }));
    const bodyRows = within(table).getAllByRole("row").slice(1);
    expect(bodyRows[0]).toHaveTextContent("Alpha job");
    expect(bodyRows[1]).toHaveTextContent("Beta job");

    await user.click(screen.getByText("Columns"));
    await user.click(screen.getByRole("checkbox", { name: "Status" }));
    expect(within(table).queryByText("queued")).not.toBeInTheDocument();
  });

  it("changes page size and exposes selected rows to toolbar actions", async () => {
    const user = userEvent.setup();
    renderTable({
      toolbarActions: ({ selectedRows }) => (
        <button className="secondary" disabled={selectedRows.length === 0}>
          Act on {selectedRows.map((row) => row.original.title).join(", ") || "none"}
        </button>
      ),
    });

    await user.selectOptions(screen.getByRole("combobox", { name: "Rows per page" }), "10");
    const table = screen.getByRole("table", { name: "Demo jobs" });
    expect(within(table).getByText("Beta job")).toBeInTheDocument();
    expect(screen.getByText("1-3 of 3")).toBeInTheDocument();

    const action = screen.getByRole("button", { name: "Act on none" });
    expect(action).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Select row alpha" }));
    expect(screen.getByRole("button", { name: "Act on Alpha job" })).toBeEnabled();
  });

  it("supports selectable rows and expandable details", async () => {
    const user = userEvent.setup();
    renderTable();

    expect(screen.getByText("0 selected")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Select row gamma" }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Expand row" })[0]);
    expect(screen.getByText("Details for Gamma job")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Collapse row" }));
    expect(screen.queryByText("Details for Gamma job")).not.toBeInTheDocument();
  });

  it("renders loading and empty states", () => {
    const { rerender } = renderTable({ loading: true });
    expect(screen.getByText("Loading data")).toBeInTheDocument();

    rerender(
      <ConsoleTable
        ariaLabel="Demo jobs"
        columns={columns}
        data={[]}
        emptyDescription="No demo rows match the current table state."
        emptyTitle="No demo rows"
        getRowId={(row) => row.id}
      />,
    );
    expect(screen.getByText("No demo rows")).toBeInTheDocument();
    expect(screen.getByText("No demo rows match the current table state.")).toBeInTheDocument();
  });
});
