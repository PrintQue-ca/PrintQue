import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { ListPlus, Pencil, Trash2 } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ResizableTable, ResizableTableHeadCell } from '@/components/ui/resizable-table'
import { TableBody, TableCell, TableHeader, TableRow } from '@/components/ui/table'
import { TruncatedText } from '@/components/ui/truncated-text'
import { useBulkDeleteLibrary, useDeleteLibraryItem } from '@/hooks'
import { formatPrintDuration } from '@/lib/format-duration'
import { resizableTableDefaultColumn, useFitTableColumns } from '@/lib/resizable-table'
import type { LibraryItem } from '@/types'
import { BulkEnqueueDialog } from './BulkEnqueueDialog'
import { BulkLibraryEditDialog } from './BulkLibraryEditDialog'
import { LibraryEditDialog } from './LibraryEditDialog'

const columnHelper = createColumnHelper<LibraryItem>()

interface LibraryTableProps {
  items: LibraryItem[]
  previewMode?: boolean
  emptyMessage?: string
}

export function LibraryTable({
  items,
  previewMode = false,
  emptyMessage = 'No items in library. Upload a file to get started.',
}: LibraryTableProps) {
  const deleteItem = useDeleteLibraryItem()
  const bulkDelete = useBulkDeleteLibrary()
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [enqueueOpen, setEnqueueOpen] = useState(false)
  const [bulkEditOpen, setBulkEditOpen] = useState(false)
  const [editItem, setEditItem] = useState<LibraryItem | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const itemIds = useMemo(() => new Set(items.map((i) => i.id)), [items])
  const effectiveSelectedIds = useMemo(
    () => new Set([...selectedIds].filter((id) => itemIds.has(id))),
    [selectedIds, itemIds]
  )
  const selectedItems = items.filter((i) => effectiveSelectedIds.has(i.id))

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    if (effectiveSelectedIds.size === items.length && items.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)))
    }
  }, [effectiveSelectedIds.size, items])

  const clearSelection = () => setSelectedIds(new Set())

  const handleBulkDelete = () => {
    if (effectiveSelectedIds.size === 0) return
    const count = effectiveSelectedIds.size
    if (!confirm(`Delete ${count} selected library item(s)?`)) return
    const ids = Array.from(effectiveSelectedIds)
    clearSelection()
    bulkDelete.mutate(ids)
  }

  const handleDelete = useCallback(
    (id: number) => {
      if (!confirm('Delete this library item?')) return
      deleteItem.mutate(id, {
        onSuccess: () => toast.success('Deleted from library'),
        onError: () => toast.error('Failed to delete'),
      })
    },
    [deleteItem]
  )

  const columns = useMemo(() => {
    const cols = []

    if (!previewMode) {
      cols.push(
        columnHelper.display({
          id: 'select',
          size: 44,
          minSize: 44,
          maxSize: 44,
          enableResizing: false,
          header: () => (
            <Checkbox
              checked={items.length > 0 && effectiveSelectedIds.size === items.length}
              onCheckedChange={toggleAll}
            />
          ),
          cell: ({ row }) => (
            <Checkbox
              checked={effectiveSelectedIds.has(row.original.id)}
              onCheckedChange={() => toggleSelect(row.original.id)}
            />
          ),
        })
      )
    }

    cols.push(
      columnHelper.accessor((row) => row.name || row.filename, {
        id: 'name',
        header: 'Name',
        size: 220,
        minSize: 100,
        cell: ({ row }) => {
          const item = row.original
          const primary = item.name || item.filename
          return (
            <TruncatedText
              text={primary}
              secondary={item.name ? item.filename : undefined}
              className="font-medium"
            />
          )
        },
      }),
      columnHelper.accessor('groups', {
        header: 'Groups',
        size: 140,
        minSize: 80,
        cell: (info) => {
          const groups = info.getValue() || ['Default']
          return (
            <div className="flex flex-wrap gap-1 min-w-0">
              {groups.map((g) => (
                <Badge key={String(g)} variant="secondary" className="text-xs max-w-full truncate">
                  {String(g)}
                </Badge>
              ))}
            </div>
          )
        },
      }),
      columnHelper.accessor('estimated_print_seconds', {
        header: 'Est. time',
        size: 100,
        minSize: 80,
        cell: (info) => (
          <span className="text-sm text-muted-foreground tabular-nums">
            {formatPrintDuration(info.getValue())}
          </span>
        ),
      }),
      columnHelper.display({
        id: 'ejection',
        header: 'Ejection',
        size: 120,
        minSize: 72,
        cell: ({ row }) => {
          const item = row.original
          const label = item.ejection_enabled ? item.ejection_code_name || 'On' : 'Off'
          return (
            <TruncatedText text={label} className="text-sm text-muted-foreground font-normal" />
          )
        },
      })
    )

    if (!previewMode) {
      cols.push(
        columnHelper.display({
          id: 'actions',
          header: '',
          size: 88,
          minSize: 88,
          maxSize: 88,
          enableResizing: false,
          cell: ({ row }) => (
            <div className="flex gap-1 justify-end">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setEditItem(row.original)}
                title="Edit"
              >
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleDelete(row.original.id)}
                title="Delete"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ),
        })
      )
    }

    return cols
  }, [
    previewMode,
    items.length,
    effectiveSelectedIds.size,
    effectiveSelectedIds,
    items,
    handleDelete,
    toggleAll,
    toggleSelect,
  ])

  const table = useReactTable({
    data: items,
    columns,
    defaultColumn: resizableTableDefaultColumn,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.id),
  })

  const columnWeights = useMemo(
    () => ({
      select: 0.5,
      name: 3,
      groups: 1.2,
      estimated_print_seconds: 0.9,
      ejection: 1,
      actions: 0.8,
    }),
    []
  )

  useFitTableColumns(table, containerRef, columnWeights)

  const colSpan = table.getVisibleLeafColumns().length + 0

  return (
    <>
      {!previewMode && effectiveSelectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-md border bg-muted/50 px-3 py-2 mb-3">
          <span className="text-sm">{effectiveSelectedIds.size} selected</span>
          <Button size="sm" onClick={() => setEnqueueOpen(true)}>
            <ListPlus className="h-4 w-4 mr-1" />
            Add to queue
          </Button>
          <Button size="sm" variant="outline" onClick={() => setBulkEditOpen(true)}>
            <Pencil className="h-4 w-4 mr-1" />
            Edit
          </Button>
          <Button size="sm" variant="destructive" onClick={handleBulkDelete}>
            <Trash2 className="h-4 w-4 mr-1" />
            Delete
          </Button>
          <Button size="sm" variant="ghost" onClick={clearSelection}>
            Clear selection
          </Button>
        </div>
      )}

      <div className="rounded-md border">
        <ResizableTable containerRef={containerRef}>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <ResizableTableHeadCell key={header.id} header={header} />
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length > 0 ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
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
                <TableCell
                  colSpan={colSpan || 1}
                  className="text-center text-muted-foreground py-8"
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </ResizableTable>
      </div>

      <BulkEnqueueDialog open={enqueueOpen} onOpenChange={setEnqueueOpen} items={selectedItems} />
      <BulkLibraryEditDialog
        open={bulkEditOpen}
        onOpenChange={setBulkEditOpen}
        items={selectedItems}
        onSuccess={clearSelection}
      />
      <LibraryEditDialog
        item={editItem}
        open={!!editItem}
        onOpenChange={(o) => !o && setEditItem(null)}
      />
    </>
  )
}
