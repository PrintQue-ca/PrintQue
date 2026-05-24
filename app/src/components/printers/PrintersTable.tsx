import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { Settings, Trash2 } from 'lucide-react'
import { useMemo, useRef } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ResizableTable, ResizableTableHeadCell } from '@/components/ui/resizable-table'
import { TableBody, TableCell, TableHeader, TableRow } from '@/components/ui/table'
import { TruncatedText } from '@/components/ui/truncated-text'
import {
  findQueueJobForPrinter,
  formatQueueJobProgressSummary,
  getPrinterQueueJobId,
  getQueueJobDisplayName,
} from '@/lib/printer-queue-job'
import { resizableTableDefaultColumn, useFitTableColumns } from '@/lib/resizable-table'
import type { Printer, QueueJob } from '@/types'

const columnHelper = createColumnHelper<Printer>()

const statusColors: Record<string, string> = {
  IDLE: 'bg-green-500',
  PRINTING: 'bg-blue-500',
  PREPARING: 'bg-blue-400',
  FINISHED: 'bg-yellow-500',
  ERROR: 'bg-red-500',
  EJECTING: 'bg-purple-500',
  COOLING: 'bg-cyan-500',
  PAUSED: 'bg-orange-500',
  OFFLINE: 'bg-gray-500',
}

interface PrintersTableProps {
  printers: Printer[]
  queueJobs: QueueJob[]
  onEdit: (printer: Printer) => void
  onDelete: (name: string) => void
  onJobClick: (printer: Printer) => void
}

export function PrintersTable({
  printers,
  queueJobs,
  onEdit,
  onDelete,
  onJobClick,
}: PrintersTableProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  const columns = useMemo(
    () => [
      columnHelper.accessor('name', {
        header: 'Name',
        size: 140,
        minSize: 80,
        cell: (info) => <TruncatedText text={info.getValue()} className="font-medium" />,
      }),
      columnHelper.accessor('ip', {
        header: 'IP Address',
        size: 120,
        minSize: 90,
        cell: (info) => <TruncatedText text={info.getValue()} />,
      }),
      columnHelper.accessor('type', {
        header: 'Type',
        size: 90,
        minSize: 72,
        cell: (info) => (
          <Badge variant="outline" className="capitalize">
            {info.getValue()}
          </Badge>
        ),
      }),
      columnHelper.accessor('status', {
        header: 'Status',
        size: 100,
        minSize: 80,
        cell: (info) => (
          <Badge className={statusColors[info.getValue()] || 'bg-gray-500'}>
            {info.getValue()}
          </Badge>
        ),
      }),
      columnHelper.display({
        id: 'job',
        header: 'Job',
        size: 180,
        minSize: 100,
        cell: ({ row }) => {
          const printer = row.original
          const jobId = getPrinterQueueJobId(printer)
          const job = jobId != null ? findQueueJobForPrinter(printer, queueJobs) : null
          if (jobId == null) return <span className="text-muted-foreground">-</span>
          const name = job ? getQueueJobDisplayName(job) : 'Unknown job'
          const secondary = job ? formatQueueJobProgressSummary(job, printers) : undefined
          return (
            <button
              type="button"
              className="text-left text-sm hover:underline min-w-0 w-full"
              onClick={() => onJobClick(printer)}
            >
              <TruncatedText text={name} secondary={secondary} />
            </button>
          )
        },
      }),
      columnHelper.display({
        id: 'progress',
        header: 'Progress',
        size: 88,
        minSize: 64,
        enableResizing: true,
        cell: ({ row }) => {
          const printer = row.original
          const text =
            printer.status === 'PRINTING' && printer.progress !== undefined
              ? `${printer.progress}%`
              : '-'
          return <span>{text}</span>
        },
      }),
      columnHelper.display({
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 96,
        minSize: 96,
        maxSize: 120,
        enableResizing: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onEdit(row.original)}
              aria-label="Edit printer"
            >
              <Settings className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => onDelete(row.original.name)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ),
      }),
    ],
    [queueJobs, printers, onEdit, onDelete, onJobClick]
  )

  const table = useReactTable({
    data: printers,
    columns,
    defaultColumn: resizableTableDefaultColumn,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.name,
  })

  useFitTableColumns(table, containerRef, {
    name: 1.2,
    ip: 1,
    type: 0.8,
    status: 1,
    job: 2,
    progress: 0.7,
    actions: 0.9,
  })

  return (
    <ResizableTable containerRef={containerRef}>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <ResizableTableHeadCell
                key={header.id}
                header={header}
                className={header.column.id === 'actions' ? 'text-right' : undefined}
              />
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow key={row.id}>
            {row.getVisibleCells().map((cell) => (
              <TableCell
                key={cell.id}
                style={{ width: cell.column.getSize() }}
                className={
                  cell.column.id === 'actions'
                    ? 'max-w-0 overflow-hidden text-right'
                    : 'max-w-0 overflow-hidden'
                }
              >
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </ResizableTable>
  )
}
