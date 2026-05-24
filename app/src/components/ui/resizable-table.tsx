import type { Header } from '@tanstack/react-table'
import { flexRender } from '@tanstack/react-table'
import type * as React from 'react'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

interface ResizableTableProps extends React.ComponentProps<'table'> {
  containerRef?: React.RefObject<HTMLDivElement | null>
  containerClassName?: string
}

/** Full-width table with fixed layout so columns respect sizing and truncate cleanly. */
export function ResizableTable({
  className,
  containerRef,
  containerClassName,
  children,
  ...props
}: ResizableTableProps) {
  return (
    <div
      ref={containerRef}
      data-slot="resizable-table-container"
      className={cn('relative w-full overflow-x-auto', containerClassName)}
    >
      <table
        data-slot="table"
        className={cn('w-full table-fixed caption-bottom text-sm', className)}
        {...props}
      >
        {children}
      </table>
    </div>
  )
}

interface TableColumnResizeHandleProps<T> {
  header: Header<T, unknown>
}

export function TableColumnResizeHandle<T>({ header }: TableColumnResizeHandleProps<T>) {
  if (!header.column.getCanResize()) return null

  return (
    <button
      type="button"
      aria-label={`Resize ${String(header.column.columnDef.header ?? 'column')}`}
      onMouseDown={header.getResizeHandler()}
      onTouchStart={header.getResizeHandler()}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        'absolute right-0 top-0 z-10 h-full w-1.5 cursor-col-resize touch-none select-none border-0 bg-transparent p-0',
        'hover:bg-primary/40',
        header.column.getIsResizing() && 'bg-primary/60'
      )}
    />
  )
}

interface ResizableTableHeadCellProps<T> {
  header: Header<T, unknown>
  className?: string
  children?: React.ReactNode
}

export function ResizableTableHeadCell<T>({
  header,
  className,
  children,
}: ResizableTableHeadCellProps<T>) {
  return (
    <TableHead
      style={{ width: header.getSize() }}
      className={cn('relative overflow-hidden', className)}
    >
      <div className="truncate pr-2">
        {children ?? flexRender(header.column.columnDef.header, header.getContext())}
      </div>
      <TableColumnResizeHandle header={header} />
    </TableHead>
  )
}

interface ResizableTableBodyProps<T> {
  table: {
    getHeaderGroups: () => ReturnType<import('@tanstack/react-table').Table<T>['getHeaderGroups']>
    getRowModel: () => ReturnType<import('@tanstack/react-table').Table<T>['getRowModel']>
  }
  /** Extra leading cells per row (e.g. drag handle) */
  leadingHead?: React.ReactNode
  leadingCell?: (row: import('@tanstack/react-table').Row<T>) => React.ReactNode
  emptyMessage?: string
  colSpanOffset?: number
}

export function ResizableTableBody<T>({
  table,
  leadingHead,
  leadingCell,
  emptyMessage = 'No results.',
  colSpanOffset = 0,
}: ResizableTableBodyProps<T>) {
  const rows = table.getRowModel().rows
  const colCount =
    table.getHeaderGroups()[0]?.headers.length ?? 0 + (leadingHead ? 1 : 0) + colSpanOffset

  return (
    <>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {leadingHead}
            {headerGroup.headers.map((header) => (
              <ResizableTableHeadCell key={header.id} header={header} />
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.length > 0 ? (
          rows.map((row) => (
            <TableRow key={row.id}>
              {leadingCell?.(row)}
              {row.getVisibleCells().map((cell) => (
                <TableCell
                  key={cell.id}
                  style={{ width: cell.column.getSize() }}
                  className="max-w-0 overflow-hidden"
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))
        ) : (
          <TableRow>
            <TableCell colSpan={colCount || 1} className="h-24 text-center text-muted-foreground">
              {emptyMessage}
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </>
  )
}
