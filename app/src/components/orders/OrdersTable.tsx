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
import {
  AlertCircle,
  GripVertical,
  Minus,
  Plus,
  Thermometer,
  Trash2,
  Zap,
  ZapOff,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { GcodeEditor } from '@/components/ui/gcode-editor'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useBulkDeleteOrders,
  useDebouncedQueueQuantity,
  useDeleteOrder,
  useEjectionCodes,
  useReorderOrder,
  useUpdateOrder,
  useUpdateOrderEjection,
} from '@/hooks'
import type { Order } from '@/types'

interface OrdersTableProps {
  orders: Order[]
}

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
  const [value, setValue] = useState<string>(
    initialValue === undefined || initialValue === null ? '' : String(initialValue)
  )

  useEffect(() => {
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
        onBlur={commit}
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
}: {
  row: { id: string; original: Order }
  children: React.ReactNode
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: row.original.id,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    // Smooth transitions while dragging for other items to shift
    transition,
    opacity: isDragging ? 0.5 : 1,
    // Lift dragged item above others
    zIndex: isDragging ? 1 : 0,
    position: 'relative' as const,
  }

  return (
    <TableRow ref={setNodeRef} style={style} className={isDragging ? 'bg-muted' : ''}>
      <TableCell className="w-10">
        <div
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing p-1 hover:bg-muted rounded"
        >
          <GripVertical className="h-4 w-4 text-muted-foreground" />
        </div>
      </TableCell>
      {children}
    </TableRow>
  )
}

export function OrdersTable({ orders }: OrdersTableProps) {
  const deleteOrder = useDeleteOrder()
  const bulkDeleteOrders = useBulkDeleteOrders()
  const reorderOrder = useReorderOrder()
  const { bumpQuantity, setQuantity, flushQuantity } = useDebouncedQueueQuantity()
  const updateOrder = useUpdateOrder()
  const updateOrderEjection = useUpdateOrderEjection()
  const { data: ejectionCodes } = useEjectionCodes()
  const [editingQuantity, setEditingQuantity] = useState<number | null>(null)
  const [quantityValue, setQuantityValue] = useState<number>(0)
  const [editingNameId, setEditingNameId] = useState<number | null>(null)
  const [nameValue, setNameValue] = useState<string>('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [customGcodeOrder, setCustomGcodeOrder] = useState<Order | null>(null)
  const [customGcodeValue, setCustomGcodeValue] = useState('')
  const [errorDetailOrder, setErrorDetailOrder] = useState<Order | null>(null)

  // Local state for immediate UI updates during drag
  const [localOrders, setLocalOrders] = useState(orders)

  // Sync with prop changes (from server/other sources)
  useEffect(() => {
    setLocalOrders(orders)
  }, [orders])

  const resolveOrderGcode = (order: Order): string => {
    if (!order.ejection_code_id) return ''
    return ejectionCodes?.find((code) => code.id === order.ejection_code_id)?.gcode || ''
  }

  const getEjectionDisplayName = (order: Order): string => {
    if (!order.ejection_enabled) return 'Off'
    if (order.ejection_code_id) {
      const preset = ejectionCodes?.find((code) => code.id === order.ejection_code_id)
      if (preset) return preset.name
    }
    return order.ejection_code_name || 'Custom'
  }

  const handleEjectionChange = async (orderId: number, codeId: string, currentOrder: Order) => {
    if (codeId === 'custom') {
      setCustomGcodeOrder(currentOrder)
      setCustomGcodeValue(resolveOrderGcode(currentOrder))
      return
    }

    try {
      if (codeId === 'none') {
        await updateOrderEjection.mutateAsync({
          id: orderId,
          ejectionEnabled: false,
          ejectionCodeId: null,
        })
        toast.success('Ejection disabled')
        return
      }

      await updateOrderEjection.mutateAsync({
        id: orderId,
        ejectionEnabled: true,
        ejectionCodeId: codeId,
      })

      const presetName = ejectionCodes?.find((code) => code.id === codeId)?.name
      toast.success(`Ejection set to "${presetName || 'preset'}"`)
    } catch {
      toast.error('Failed to update ejection settings')
    }
  }

  const handleSaveCustomGcode = async () => {
    if (!customGcodeOrder) return
    try {
      await updateOrderEjection.mutateAsync({
        id: customGcodeOrder.id,
        ejectionEnabled: true,
        endGcode: customGcodeValue,
      })
      toast.success('Custom ejection G-code saved')
      setCustomGcodeOrder(null)
      setCustomGcodeValue('')
    } catch {
      toast.error('Failed to save custom ejection G-code')
    }
  }

  const handleCooldownTempChange = async (orderId: number, cooldownTemp: number | null) => {
    try {
      await updateOrderEjection.mutateAsync({ id: orderId, cooldownTemp })
      toast.success(
        cooldownTemp === null ? 'Cooldown removed' : `Cooldown set to ${cooldownTemp}°C`
      )
    } catch {
      toast.error('Failed to update cooldown temperature')
    }
  }

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

  const handleDelete = (id: number) => {
    if (confirm('Are you sure you want to delete this order?')) {
      deleteOrder.mutate(id)
    }
  }

  const handleQuantityChange = (id: number, currentQuantity: number) => {
    setEditingQuantity(id)
    setQuantityValue(currentQuantity)
  }

  const handleQuantitySubmit = (id: number) => {
    if (quantityValue >= 0) {
      setQuantity(id, quantityValue)
      flushQuantity(id)
    }
    setEditingQuantity(null)
  }

  const handleQuantityIncrement = (id: number) => {
    bumpQuantity(id, 1)
  }

  const handleQuantityDecrement = (id: number) => {
    bumpQuantity(id, -1)
  }

  const handleNameChange = (order: Order) => {
    setEditingNameId(order.id)
    setNameValue(order.name ?? order.filename)
  }

  const handleNameSubmit = (id: number) => {
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
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = localOrders.findIndex((order) => order.id === active.id)
      const newIndex = localOrders.findIndex((order) => order.id === over.id)

      if (oldIndex !== -1 && newIndex !== -1) {
        // Update local state immediately (synchronous - no flicker)
        setLocalOrders(arrayMove(localOrders, oldIndex, newIndex))
        // Then persist to server
        reorderOrder.mutate({ id: active.id as number, newIndex })
      }
    }
  }

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === localOrders.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(localOrders.map((o) => o.id)))
    }
  }

  const handleBulkDelete = () => {
    if (selectedIds.size === 0) return
    if (!confirm(`Delete ${selectedIds.size} selected order(s)?`)) return
    const ids = Array.from(selectedIds)
    const count = ids.length
    setSelectedIds(new Set())
    bulkDeleteOrders.mutate(ids, {
      onSuccess: (data) => {
        toast.success(`${data?.deleted_count ?? count} order(s) deleted`)
      },
    })
  }

  const columns = [
    columnHelper.display({
      id: 'select',
      header: () => (
        <Checkbox
          checked={localOrders.length > 0 && selectedIds.size === localOrders.length}
          onCheckedChange={toggleSelectAll}
          aria-label="Select all"
        />
      ),
      cell: (info) => (
        <Checkbox
          checked={selectedIds.has(info.row.original.id)}
          onCheckedChange={() => toggleSelect(info.row.original.id)}
          aria-label={`Select order ${info.row.original.id}`}
        />
      ),
    }),
    columnHelper.accessor('priority', {
      header: '#',
      cell: (info) => (
        <span className="font-medium text-muted-foreground">{info.row.index + 1}</span>
      ),
    }),
    columnHelper.accessor('filename', {
      header: 'Name',
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
            className="flex flex-col text-left hover:bg-muted rounded px-1 -mx-1 py-0.5 -my-0.5 min-w-0"
          >
            <span className="truncate max-w-[200px] block" title={displayName}>
              {displayName}
            </span>
            {name && (
              <span
                className="text-xs text-muted-foreground truncate max-w-[200px] block"
                title={filename}
              >
                {filename}
              </span>
            )}
          </button>
        )
      },
    }),
    columnHelper.accessor('quantity', {
      header: 'Qty',
      cell: (info) => {
        const id = info.row.original.id
        const currentQty = info.getValue()

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
              className="cursor-pointer min-w-[2rem] text-center"
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
    columnHelper.accessor('sent', {
      header: 'Sent',
      cell: (info) => {
        const order = info.row.original
        const sent = info.getValue()
        const total = order.quantity
        const lastError = order.last_error
        const tooltipParts = [
          lastError,
          order.last_error_printer ? `Printer: ${order.last_error_printer}` : null,
          order.last_error_at ? new Date(order.last_error_at).toLocaleString() : null,
        ].filter(Boolean)
        return (
          <div className="flex items-center gap-1.5">
            <span className={sent >= total ? 'text-green-600 font-medium' : ''}>
              {sent}/{total}
            </span>
            {lastError ? (
              <button
                type="button"
                className="inline-flex text-amber-600 hover:text-amber-700"
                title={tooltipParts.join(' — ')}
                aria-label="View start error details"
                onClick={() => setErrorDetailOrder(order)}
              >
                <AlertCircle className="h-4 w-4 shrink-0" />
              </button>
            ) : null}
          </div>
        )
      },
    }),
    columnHelper.accessor('groups', {
      header: 'Groups',
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
      cell: (info) => {
        const order = info.row.original
        const isEnabled = order.ejection_enabled
        const codeName = getEjectionDisplayName(order)
        const codeId = order.ejection_code_id
        const cooldownTemp = order.cooldown_temp

        let currentValue = 'none'
        if (isEnabled) {
          if (codeId && ejectionCodes?.find((c) => c.id === codeId)) {
            currentValue = codeId
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
              <SelectTrigger className="w-[130px] h-8 text-xs">
                <SelectValue>
                  <span className="flex items-center gap-1">
                    {isEnabled ? (
                      <>
                        <Zap className="h-3 w-3 text-yellow-500" />
                        <span className="truncate">{codeName}</span>
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
  ]

  const table = useReactTable({
    data: localOrders,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.id),
  })

  return (
    <div className="space-y-2">
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-md border bg-muted/50 px-3 py-2">
          <span className="text-sm font-medium">{selectedIds.size} selected</span>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleBulkDelete}
            disabled={bulkDeleteOrders.isPending}
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Delete selected
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
            Clear selection
          </Button>
        </div>
      )}
      <div className="rounded-md border">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  <TableHead className="w-10"></TableHead>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows?.length ? (
                <SortableContext
                  items={localOrders.map((o) => o.id)}
                  strategy={verticalListSortingStrategy}
                >
                  {table.getRowModel().rows.map((row) => (
                    <SortableRow key={row.id} row={row}>
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </SortableRow>
                  ))}
                </SortableContext>
              ) : (
                <TableRow>
                  <TableCell colSpan={columns.length + 1} className="h-24 text-center">
                    No jobs in queue.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </DndContext>
      </div>

      <Dialog
        open={errorDetailOrder !== null}
        onOpenChange={(open) => !open && setErrorDetailOrder(null)}
      >
        <DialogContent className="max-w-lg max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Start error</DialogTitle>
            <DialogDescription>
              {errorDetailOrder
                ? `${errorDetailOrder.name || errorDetailOrder.filename} (job #${errorDetailOrder.id})`
                : ''}
            </DialogDescription>
          </DialogHeader>
          {errorDetailOrder?.last_error ? (
            <p className="text-sm text-destructive">{errorDetailOrder.last_error}</p>
          ) : null}
          <div className="text-xs text-muted-foreground space-y-1">
            {errorDetailOrder?.last_error_printer ? (
              <p>Printer: {errorDetailOrder.last_error_printer}</p>
            ) : null}
            {errorDetailOrder?.last_error_phase ? (
              <p>Phase: {errorDetailOrder.last_error_phase}</p>
            ) : null}
            {errorDetailOrder?.last_error_at ? (
              <p>Last seen: {new Date(errorDetailOrder.last_error_at).toLocaleString()}</p>
            ) : null}
          </div>
          {(errorDetailOrder?.error_events?.length ?? 0) > 0 ? (
            <div className="flex-1 min-h-0 overflow-y-auto border rounded-md p-2 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Recent events</p>
              {[...(errorDetailOrder?.error_events ?? [])].reverse().map((evt, idx) => (
                <div
                  key={`${evt.at}-${idx}`}
                  className="text-xs border-b last:border-0 pb-2 last:pb-0"
                >
                  <p className="text-muted-foreground">{new Date(evt.at).toLocaleString()}</p>
                  <p>{evt.message}</p>
                  {evt.printer ? (
                    <p className="text-muted-foreground">Printer: {evt.printer}</p>
                  ) : null}
                  {evt.phase ? <p className="text-muted-foreground">Phase: {evt.phase}</p> : null}
                  {evt.batch_id ? (
                    <p className="text-muted-foreground">Batch: {evt.batch_id}</p>
                  ) : null}
                  {evt.task_id ? (
                    <p className="text-muted-foreground">Task: {evt.task_id}</p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setErrorDetailOrder(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={customGcodeOrder !== null}
        onOpenChange={(open) => !open && setCustomGcodeOrder(null)}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Custom ejection G-code</DialogTitle>
            <DialogDescription>
              {customGcodeOrder
                ? `Edit ejection sequence for ${customGcodeOrder.name || customGcodeOrder.filename}`
                : ''}
            </DialogDescription>
          </DialogHeader>
          <GcodeEditor
            value={customGcodeValue}
            onChange={setCustomGcodeValue}
            className="flex-1 min-h-[300px]"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCustomGcodeOrder(null)}>
              Cancel
            </Button>
            <Button onClick={handleSaveCustomGcode} disabled={!customGcodeValue.trim()}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default OrdersTable
