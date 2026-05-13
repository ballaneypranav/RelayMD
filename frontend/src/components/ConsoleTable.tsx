import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Columns3,
  Filter,
  Search,
} from "lucide-react";
import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ExpandedState,
  type PaginationState,
  type Row,
  type RowSelectionState,
  type SortingState,
  type Table,
  type VisibilityState,
} from "@tanstack/react-table";

export interface ConsoleTableToolbarContext<TData> {
  selectedRows: Row<TData>[];
  table: Table<TData>;
}

export interface ConsoleTableProps<TData> {
  ariaLabel: string;
  data: TData[];
  columns: ColumnDef<TData>[];
  getRowId: (row: TData, index: number) => string;
  emptyTitle: string;
  emptyDescription: string;
  loading?: boolean;
  searchPlaceholder?: string;
  filterControls?: ReactNode;
  toolbarActions?: ReactNode | ((context: ConsoleTableToolbarContext<TData>) => ReactNode);
  initialPageSize?: number;
  pageSizeOptions?: number[];
  enableSelection?: boolean;
  renderExpandedRow?: (row: Row<TData>) => ReactNode;
}

interface CompactIconButtonProps {
  label: string;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}

interface IndeterminateCheckboxProps {
  label: string;
  checked: boolean;
  disabled?: boolean;
  indeterminate?: boolean;
  onChange: () => void;
}

function IndeterminateCheckbox({
  label,
  checked,
  disabled = false,
  indeterminate = false,
  onChange,
}: IndeterminateCheckboxProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.indeterminate = indeterminate;
    }
  }, [indeterminate]);

  return (
    <input
      aria-label={label}
      checked={checked}
      disabled={disabled}
      onChange={onChange}
      ref={inputRef}
      type="checkbox"
    />
  );
}

export function CompactIconButton({
  label,
  children,
  className = "",
  disabled = false,
  onClick,
  type = "button",
}: CompactIconButtonProps) {
  return (
    <button
      aria-label={label}
      className={`icon-button ${className}`.trim()}
      disabled={disabled}
      onClick={onClick}
      title={label}
      type={type}
    >
      {children}
    </button>
  );
}

export function ConsoleTableEmptyState({
  title,
  description,
  loading = false,
}: {
  title: string;
  description: string;
  loading?: boolean;
}) {
  return (
    <div className="empty-state console-table-empty">
      <h3>{loading ? "Loading data" : title}</h3>
      <p>{loading ? "Fetching the latest operator data." : description}</p>
    </div>
  );
}

export function ConsoleTable<TData>({
  ariaLabel,
  data,
  columns,
  getRowId,
  emptyTitle,
  emptyDescription,
  loading = false,
  searchPlaceholder = "Search table",
  filterControls,
  toolbarActions,
  initialPageSize = 10,
  pageSizeOptions = [10, 25, 50],
  enableSelection = false,
  renderExpandedRow,
}: ConsoleTableProps<TData>) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: initialPageSize,
  });

  const tableColumns = useMemo<ColumnDef<TData>[]>(() => {
    const selectionColumn: ColumnDef<TData> = {
      id: "__select",
      header: ({ table }) => (
        <IndeterminateCheckbox
          checked={table.getIsAllPageRowsSelected()}
          indeterminate={table.getIsSomePageRowsSelected()}
          label="Select all rows"
          onChange={() => table.toggleAllPageRowsSelected()}
        />
      ),
      cell: ({ row }) => (
        <IndeterminateCheckbox
          checked={row.getIsSelected()}
          disabled={!row.getCanSelect()}
          label={`Select row ${row.id}`}
          onChange={() => row.toggleSelected()}
        />
      ),
      enableHiding: false,
      enableSorting: false,
      size: 44,
    };

    const expansionColumn: ColumnDef<TData> = {
      id: "__expand",
      header: "",
      cell: ({ row }) =>
        row.getCanExpand() ? (
          <CompactIconButton
            label={row.getIsExpanded() ? "Collapse row" : "Expand row"}
            onClick={() => row.toggleExpanded()}
          >
            {row.getIsExpanded() ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </CompactIconButton>
        ) : null,
      enableHiding: false,
      enableSorting: false,
      size: 44,
    };

    return [
      ...(enableSelection ? [selectionColumn] : []),
      ...(renderExpandedRow ? [expansionColumn] : []),
      ...columns,
    ];
  }, [columns, enableSelection, renderExpandedRow]);

  const table = useReactTable({
    data,
    columns: tableColumns,
    state: {
      columnVisibility,
      expanded,
      globalFilter,
      pagination,
      rowSelection,
      sorting,
    },
    enableRowSelection: enableSelection,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowCanExpand: () => Boolean(renderExpandedRow),
    getRowId,
    getSortedRowModel: getSortedRowModel(),
    globalFilterFn: "includesString",
    onColumnVisibilityChange: setColumnVisibility,
    onExpandedChange: setExpanded,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    onRowSelectionChange: setRowSelection,
    onSortingChange: setSorting,
  });

  const visibleColumns = table.getAllLeafColumns().filter((column) => column.getCanHide());
  const selectedRows = table.getSelectedRowModel().rows;
  const selectedCount = selectedRows.length;
  const totalRows = table.getFilteredRowModel().rows.length;
  const pageStart = totalRows === 0 ? 0 : pagination.pageIndex * pagination.pageSize + 1;
  const pageEnd = Math.min(totalRows, (pagination.pageIndex + 1) * pagination.pageSize);
  const normalizedPageSizeOptions = Array.from(new Set([...pageSizeOptions, initialPageSize])).sort(
    (left, right) => left - right,
  );
  const renderedToolbarActions =
    typeof toolbarActions === "function" ? toolbarActions({ selectedRows, table }) : toolbarActions;

  return (
    <div className="console-table-surface">
      <div className="console-table-toolbar">
        <label className="console-table-search">
          <Search aria-hidden="true" size={16} />
          <input
            aria-label="Search table"
            onChange={(event) => {
              setGlobalFilter(event.target.value);
              table.setPageIndex(0);
            }}
            placeholder={searchPlaceholder}
            type="search"
            value={globalFilter}
          />
        </label>

        <div className="console-table-tools">
          {filterControls ? (
            <details className="table-menu">
              <summary>
                <Filter aria-hidden="true" size={16} />
                Filters
              </summary>
              <div className="table-menu-panel">{filterControls}</div>
            </details>
          ) : null}

          <details className="table-menu">
            <summary>
              <Columns3 aria-hidden="true" size={16} />
              Columns
            </summary>
            <div className="table-menu-panel">
              {visibleColumns.map((column) => (
                <label className="table-menu-check" key={column.id}>
                  <input
                    checked={column.getIsVisible()}
                    onChange={column.getToggleVisibilityHandler()}
                    type="checkbox"
                  />
                  <span>{String(column.columnDef.header ?? column.id)}</span>
                </label>
              ))}
            </div>
          </details>

          {enableSelection ? <span className="selection-count">{selectedCount} selected</span> : null}
          {renderedToolbarActions}
        </div>
      </div>

      {loading || table.getRowModel().rows.length === 0 ? (
        <ConsoleTableEmptyState
          description={emptyDescription}
          loading={loading}
          title={emptyTitle}
        />
      ) : (
        <div className="table-wrap console-table-wrap">
          <table aria-label={ariaLabel} className="console-table">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} style={{ width: header.getSize() }}>
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button className="table-sort-button" onClick={header.column.getToggleSortingHandler()}>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          <ChevronsUpDown aria-hidden="true" size={14} />
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className={row.getIsSelected() ? "row-active" : undefined}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                  {row.getIsExpanded() && renderExpandedRow ? (
                    <tr className="console-table-expanded" key={`${row.id}-expanded`}>
                      <td colSpan={row.getVisibleCells().length}>{renderExpandedRow(row)}</td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="console-table-footer">
        <span>
          {pageStart}-{pageEnd} of {totalRows}
        </span>
        <div className="console-table-page-controls">
          <label className="console-table-page-size">
            Rows
            <select
              aria-label="Rows per page"
              onChange={(event) => table.setPageSize(Number(event.target.value))}
              value={pagination.pageSize}
            >
              {normalizedPageSizeOptions.map((pageSize) => (
                <option key={pageSize} value={pageSize}>
                  {pageSize}
                </option>
              ))}
            </select>
          </label>
          <button className="secondary" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>
            <ChevronLeft aria-hidden="true" size={16} />
            Previous
          </button>
          <span>
            Page {pagination.pageIndex + 1} of {Math.max(table.getPageCount(), 1)}
          </span>
          <button className="secondary" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>
            Next
            <ChevronRight aria-hidden="true" size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
