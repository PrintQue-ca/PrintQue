import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { GripVertical, Minus, Plus, Thermometer, Trash2, Zap, ZapOff } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ResizableTable, ResizableTableHeadCell } from '@/components/ui/resizable-table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { TruncatedText } from '@/components/ui/truncated-text'
import {
  useDebouncedQueueQuantity,
  useDeleteOrder,
  useEjectionCodes,
  useReorderOrder,
  useUpdateOrder,
  useUpdateQueueEjection,
} from '@/hooks'
import { getQueueJobActivity } from '@/lib/printer-queue-job'
import { resizableTableDefaultColumn, useFitTableColumns } from '@/lib/resizable-table'
import type { Order, Printer } from '@/types'

const columnHelper = createColumnHelper<Order>()

// Helper to reorder array
function arrayMove<T>(array: T[], from: number, to: number): T[] {
  const newArray = [...array]
  const [item] = newArray.splice(from, 1)
  newArray.splice(to, 0, item)
  return newArray
}

// Inline editor for an order's cooldown temperature (Bambu bed-cool target).
function CooldownTempInput({
  orderId,
  initialValue,
  onSave,
}: {
  orderId: number
  initialValue: number | null | undefined
  onSave: (orderId: number, value: number | null) => Promise<void>
}) {
  const isFocusedRef = useRef(false)
  const [value, setValue] = useState<string>(
    initialValue === undefined || initialValue === null ? '' : String(initialValue)
  )

  useEffect(() => {
    if (isFocusedRef.current) return
    setValue(initialValue === undefined || initialValue === null ? '' : String(initialValue))
  }, [initialValue])

  const commit = async () => {
    const trimmed = value.trim()
    const previous = initialValue ?? null
    let next: number | null
    if (trimmed === '') {
      next = null
    } else {
      const parsed = Number.parseInt(trimmed, 10)
      if (Number.isNaN(parsed) || parsed < 0 || parsed > 100) {
        toast.error('Cooldown must be between 0 and 100 °C')
        setValue(previous === null ? '' : String(previous))
        return
      }
      next = parsed
    }
    if (next === previous) return
    await onSave(orderId, next)
  }

  return (
    <div
      className="flex items-center h-6 px-1.5 text-xs rounded-md border border-cyan-300 text-cyan-600 gap-0.5"
      title="Bed cooldown target before ejection (Bambu only)"
    >
      <Thermometer className="h-3 w-3" />
      <Input
        type="number"
        inputMode="numeric"
        min={0}
        max={100}
        value={value}
        placeholder="—"
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => {
          isFocusedRef.current = true
        }}
        onBlur={() => {
          void commit().finally(() => {
            isFocusedRef.current = false
          })
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            ;(e.target as HTMLInputElement).blur()
          } else if (e.key === 'Escape') {
            setValue(
              initialValue === undefined || initialValue === null ? '' : String(initialValue)
            )
            ;(e.target as HTMLInputElement).blur()
          }
        }}
        className="h-5 w-10 px-1 text-xs border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
      />
      <span aria-hidden="true">°</span>
    </div>
  )
}

// Sortable row component
function SortableRow({
  row,
  children,
  dragDisabled,
}: {
  row: { id: string; original: Order }
  children: React.ReactNode
  dragDisabled?: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: row.original.id,
    disabled: dragDisabled,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 1 : 0,
    position: 'relative' as const,
  }

  return (
    <TableRow ref={setNodeRef} style={style} className={isDragging ? 'bg-muted' : ''}>
      <TableCell className="w-10">
        {!dragDisabled && (
          <div
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing p-1 hover:bg-muted rounded"
          >
            <GripVertical className="h-4 w-4 text-muted-foreground" />
          </div>
        )}
      </TableCell>
      {children}
    </TableRow>
  )
}

interface OrdersTableProps {
  orders: Order[]
  /** Canonical API queue order for drag-reorder mutations */
  allOrders?: Order[]
  /** Newest-first list for # column (full filtered set when paginated) */
  displayOrders?: Order[]
  printers?: Printer[]
  previewMode?: boolean
  emptyMessage?: string
}

export function OrdersTable({
  orders: displayedOrders,
  allOrders,
  displayOrders,
  printers = [],
  previewMode = false,
  emptyMessage = 'No items in queue.',
}: OrdersTableProps) {
  const deleteOrder = useDeleteOrder()
  const reorderOrder = useReorderOrder()
  const { bumpQuantity, setQuantity, flushQuantity } = useDebouncedQueueQuantity()
  const updateOrder = useUpdateOrder()
  const updateQueueEjection = useUpdateQueueEjection()
  const { data: ejectionCodes } = useEjectionCodes()
  const [editingQuantity, setEditingQuantity] = useState<number | null>(null)
  const [quantityValue, setQuantityValue] = useState<number>(0)
  const [editingNameId, setEditingNameId] = useState<number | null>(null)
  const [nameValue, setNameValue] = useState<string>('')
  const containerRef = useRef<HTMLDivElement>(null)

  const canonicalOrders = allOrders ?? displayedOrders
  const rankOrders = displayOrders ?? displayedOrders

  // Local state for immediate UI updates during drag (canonical queue order)
  const [localOrders, setLocalOrders] = useState(canonicalOrders)

  useEffect(() => {
    setLocalOrders(canonicalOrders)
  }, [canonicalOrders])

  const queuePosition = useCallback(
    (orderId: number) => rankOrders.findIndex((o) => o.id === orderId) + 1,
    [rankOrders]
  )

  const handleEjectionChange = useCallback(
    async (orderId: number, codeId: string, currentOrder: Order) => {
      try {
        let ejectionEnabled = true
        let ejectionCodeId: string | undefined
        let ejectionCodeName: string | undefined
        let endGcode: string | undefined

        if (codeId === 'none') {
          ejectionEnabled = false
          ejectionCodeName = undefined
          endGcode = ''
        } else if (codeId === 'custom') {
          // Keep current gcode, just mark as custom
          ejectionCodeName = 'Custom'
          endGcode = currentOrder.end_gcode
        } else {
          // Find the selected ejection code
          const selectedCode = ejectionCodes?.find((code) => code.id === codeId)
          if (selectedCode) {
            ejectionCodeId = selectedCode.id
            ejectionCodeName = selectedCode.name
            endGcode = selectedCode.gcode
          }
        }

        await updateQueueEjection.mutateAsync({
          id: orderId,
          ejectionEnabled,
          ejectionCodeId,
          endGcode,
        })

        toast.success(
          ejectionEnabled ? `Ejection set to "${ejectionCodeName}"` : 'Ejection disabled'
        )
      } catch {
        toast.error('Failed to update ejection settings')
      }
    },
    [ejectionCodes, updateQueueEjection]
  )

  const handleCooldownTempChange = useCallback(
    async (orderId: number, cooldownTemp: number | null) => {
      try {
        await updateQueueEjection.mutateAsync({ id: orderId, cooldownTemp })
        toast.success(
          cooldownTemp === null ? 'Cooldown removed' : `Cooldown set to ${cooldownTemp}°C`
        )
      } catch {
        toast.error('Failed to update cooldown temperature')
      }
    },
    [updateQueueEjection]
  )

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const handleDelete = useCallback(
    (id: number) => {
      if (confirm('Are you sure you want to delete this order?')) {
        deleteOrder.mutate(id)
      }
    },
    [deleteOrder]
  )

  const handleQuantityChange = useCallback((id: number, currentQuantity: number) => {
    setEditingQuantity(id)
    setQuantityValue(currentQuantity)
  }, [])

  const handleQuantitySubmit = useCallback(
    (id: number) => {
      if (quantityValue >= 0) {
        setQuantity(id, quantityValue)
        flushQuantity(id)
      }
      setEditingQuantity(null)
    },
    [quantityValue, setQuantity, flushQuantity]
  )

  const handleQuantityIncrement = useCallback(
    (id: number) => {
      bumpQuantity(id, 1)
    },
    [bumpQuantity]
  )

  const handleQuantityDecrement = useCallback(
    (id: number) => {
      bumpQuantity(id, -1)
    },
    [bumpQuantity]
  )

  const handleNameChange = useCallback((order: Order) => {
    setEditingNameId(order.id)
    setNameValue(order.name ?? order.filename)
  }, [])

  const handleNameSubmit = useCallback(
    (id: number) => {
      const trimmed = nameValue.trim()
      updateOrder.mutate(
        { id, data: { name: trimmed || '' } },
        {
          onSuccess: () => {
            toast.success(trimmed ? 'Name updated' : 'Name cleared')
          },
          onError: () => {
            toast.error('Failed to update name')
          },
        }
      )
      setEditingNameId(null)
    },
    [nameValue, updateOrder]
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = localOrders.findIndex((order) => order.id === active.id)
      const newIndex = localOrders.findIndex((order) => order.id === over.id)

      if (oldIndex !== -1 && newIndex !== -1) {
        setLocalOrders(arrayMove(localOrders, oldIndex, newIndex))
        reorderOrder.mutate({ id: active.id as number, newIndex })
      }
    }
  }

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'priority',
        header: '#',
        size: 48,
        minSize: 40,
        maxSize: 64,
        enableResizing: false,
        cell: (info) => (
          <span className="font-medium text-muted-foreground">
            {queuePosition(info.row.original.id)}
          </span>
        ),
      }),
      columnHelper.accessor('filename', {
        header: 'Name',
        size: 220,
        minSize: 120,
        cell: (info) => {
          const order = info.row.original
          const name = order.name
          const filename = info.getValue()
          const displayName = name || filename
          const id = order.id

          if (editingNameId === id) {
            return (
              <Input
                value={nameValue}
                onChange={(e) => setNameValue(e.target.value)}
                onBlur={() => handleNameSubmit(id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleNameSubmit(id)
                  if (e.key === 'Escape') {
                    setNameValue(name ?? filename)
                    setEditingNameId(null)
                  }
                }}
                className="max-w-[200px] h-8"
                autoFocus
              />
            )
          }

          return (
            <button
              type="button"
              onClick={() => handleNameChange(order)}
              className="block w-full min-w-0 text-left hover:bg-muted rounded px-1 -mx-1 py-0.5 -my-0.5"
            >
              <TruncatedText
                text={displayName}
                secondary={name ? filename : undefined}
                className="font-medium"
              />
            </button>
          )
        },
      }),
      columnHelper.accessor('quantity', {
        header: 'Total',
        size: 110,
        minSize: 90,
        enableResizing: true,
        cell: (info) => {
          const id = info.row.original.id
          const currentQty = info.getValue()

          if (previewMode) {
            return <span className="tabular-nums">{currentQty}</span>
          }

          if (editingQuantity === id) {
            return (
              <Input
                type="number"
                min={0}
                value={quantityValue}
                onChange={(e) => setQuantityValue(Math.max(0, parseInt(e.target.value, 10) || 0))}
                onBlur={() => handleQuantitySubmit(id)}
                onKeyDown={(e) => e.key === 'Enter' && handleQuantitySubmit(id)}
                className="w-16 h-8"
                autoFocus
              />
            )
          }

          return (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={() => handleQuantityDecrement(id)}
              >
                <Minus className="h-3 w-3" />
              </Button>
              <span
                className="cursor-pointer min-w-[2rem] text-center tabular-nums"
                onClick={() => handleQuantityChange(id, currentQty)}
              >
                {currentQty}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={() => handleQuantityIncrement(id)}
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>
          )
        },
      }),
      columnHelper.display({
        id: 'completed',
        header: 'Completed',
        size: 80,
        minSize: 64,
        cell: (info) => {
          const activity = getQueueJobActivity(info.row.original, printers)
          const done = activity.completed + activity.inProgress >= activity.total
          return (
            <span
              className={`tabular-nums ${done ? 'text-green-600 font-medium' : ''}`}
              title={`${activity.completed} of ${activity.total} total · ${activity.pending} pending`}
            >
              {activity.completed}
            </span>
          )
        },
      }),
      columnHelper.display({
        id: 'inProgress',
        header: 'In progress',
        size: 88,
        minSize: 72,
        cell: (info) => {
          const activity = getQueueJobActivity(info.row.original, printers)
          return (
            <span
              className={`tabular-nums ${activity.inProgress > 0 ? 'text-blue-600 font-medium' : ''}`}
            >
              {activity.inProgress}
            </span>
          )
        },
      }),
      columnHelper.accessor('groups', {
        header: 'Groups',
        size: 120,
        minSize: 72,
        cell: (info) => {
          const groups = info.getValue()
          if (!groups || groups.length === 0)
            return <span className="text-muted-foreground">All</span>
          return (
            <div className="flex gap-1 flex-wrap">
              {groups.map((g) => (
                <Badge key={g} variant="secondary" className="text-xs">
                  {g}
                </Badge>
              ))}
            </div>
          )
        },
      }),
      columnHelper.display({
        id: 'ejection',
        header: 'Ejection',
        size: 160,
        minSize: 120,
        cell: (info) => {
          const order = info.row.original
          const isEnabled = order.ejection_enabled
          const codeName = order.ejection_code_name
          const codeId = order.ejection_code_id
          const cooldownTemp = order.cooldown_temp

          // Determine current value for select
          let currentValue = 'none'
          if (isEnabled) {
            if (codeId && ejectionCodes?.find((c) => c.id === codeId)) {
              currentValue = codeId
            } else if (codeName === 'Custom' || (!codeId && order.end_gcode)) {
              currentValue = 'custom'
            } else {
              currentValue = 'custom'
            }
          }

          return (
            <div className="flex items-center gap-1">
              <Select
                value={currentValue}
                onValueChange={(value) => handleEjectionChange(order.id, value, order)}
              >
                <SelectTrigger className="w-full max-w-full min-w-0 h-8 text-xs">
                  <SelectValue>
                    <span className="flex items-center gap-1">
                      {isEnabled ? (
                        <>
                          <Zap className="h-3 w-3 text-yellow-500" />
                          <span className="truncate">{codeName || 'Custom'}</span>
                        </>
                      ) : (
                        <>
                          <ZapOff className="h-3 w-3 text-muted-foreground" />
                          <span>Off</span>
                        </>
                      )}
                    </span>
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">
                    <span className="flex items-center gap-2">
                      <ZapOff className="h-3 w-3" />
                      Off
                    </span>
                  </SelectItem>
                  <SelectItem value="custom">
                    <span className="flex items-center gap-2">
                      <Zap className="h-3 w-3" />
                      Custom
                    </span>
                  </SelectItem>
                  {ejectionCodes && ejectionCodes.length > 0 && (
                    <>
                      <div className="px-2 py-1 text-xs font-semibold text-muted-foreground border-t mt-1">
                        Saved Codes
                      </div>
                      {ejectionCodes.map((code) => (
                        <SelectItem key={code.id} value={code.id}>
                          <span className="flex items-center gap-2">
                            <Zap className="h-3 w-3" />
                            {code.name}
                          </span>
                        </SelectItem>
                      ))}
                    </>
                  )}
                </SelectContent>
              </Select>
              {/* Inline editor for cooldown target temperature (only meaningful when ejection enabled) */}
              {isEnabled && (
                <CooldownTempInput
                  orderId={order.id}
                  initialValue={cooldownTemp}
                  onSave={handleCooldownTempChange}
                />
              )}
            </div>
          )
        },
      }),
      columnHelper.display({
        id: 'actions',
        header: '',
        size: 48,
        minSize: 48,
        maxSize: 48,
        enableResizing: false,
        cell: (info) => (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-destructive hover:text-destructive"
            onClick={() => handleDelete(info.row.original.id)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ),
      }),
    ],
    [
      editingNameId,
      nameValue,
      editingQuantity,
      quantityValue,
      ejectionCodes,
      printers,
      previewMode,
      handleCooldownTempChange,
      handleDelete,
      handleEjectionChange,
      handleNameChange,
      handleNameSubmit,
      handleQuantityChange,
      handleQuantityDecrement,
      handleQuantityIncrement,
      handleQuantitySubmit,
      queuePosition,
    ]
  )

  const table = useReactTable({
    data: displayedOrders,
    columns,
    defaultColumn: resizableTableDefaultColumn,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.id),
  })

  useFitTableColumns(table, containerRef, {
    priority: 0.4,
    filename: 3,
    quantity: 1,
    completed: 0.6,
    inProgress: 0.6,
    groups: 1,
    ejection: 1.5,
    actions: 0.4,
  })

  const colSpan = columns.length + (previewMode ? 0 : 1)
  const dragDisabled = previewMode

  const tableBody = (
    <TableBody>
      {table.getRowModel().rows?.length ? (
        previewMode ? (
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
          <SortableContext
            items={displayedOrders.map((o) => o.id)}
            strategy={verticalListSortingStrategy}
          >
            {table.getRowModel().rows.map((row) => (
              <SortableRow key={row.id} row={row} dragDisabled={dragDisabled}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    style={{ width: cell.column.getSize() }}
                    className="max-w-0 overflow-hidden"
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </SortableRow>
            ))}
          </SortableContext>
        )
      ) : (
        <TableRow>
          <TableCell colSpan={colSpan} className="h-24 text-center text-muted-foreground">
            {emptyMessage}
          </TableCell>
        </TableRow>
      )}
    </TableBody>
  )

  const tableHeader = (
    <TableHeader>
      {table.getHeaderGroups().map((headerGroup) => (
        <TableRow key={headerGroup.id}>
          {!previewMode && (
            <TableHead className="w-10 relative" style={{ width: 40 }}>
              <span className="sr-only">Reorder</span>
            </TableHead>
          )}
          {headerGroup.headers.map((header) => (
            <ResizableTableHeadCell key={header.id} header={header} />
          ))}
        </TableRow>
      ))}
    </TableHeader>
  )

  if (previewMode) {
    return (
      <div className="rounded-md border">
        <ResizableTable containerRef={containerRef}>
          {tableHeader}
          {tableBody}
        </ResizableTable>
      </div>
    )
  }

  return (
    <div className="rounded-md border">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <ResizableTable containerRef={containerRef}>
          {tableHeader}
          {tableBody}
        </ResizableTable>
      </DndContext>
    </div>
  )
}

export default OrdersTable
