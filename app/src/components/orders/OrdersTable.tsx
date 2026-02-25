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
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
  useDeleteOrder,
  useEjectionCodes,
  useReorderOrder,
  useUpdateOrder,
  useUpdateOrderEjection,
  useUpdateQuantity,
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
  const updateQuantity = useUpdateQuantity()
  const updateOrder = useUpdateOrder()
  const updateOrderEjection = useUpdateOrderEjection()
  const { data: ejectionCodes } = useEjectionCodes()
  const [editingQuantity, setEditingQuantity] = useState<number | null>(null)
  const [quantityValue, setQuantityValue] = useState<number>(0)
  const [editingNameId, setEditingNameId] = useState<number | null>(null)
  const [nameValue, setNameValue] = useState<string>('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // Local state for immediate UI updates during drag
  const [localOrders, setLocalOrders] = useState(orders)

  // Sync with prop changes (from server/other sources)
  useEffect(() => {
    setLocalOrders(orders)
  }, [orders])

  const handleEjectionChange = async (orderId: number, codeId: string, currentOrder: Order) => {
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

      await updateOrderEjection.mutateAsync({
        id: orderId,
        ejectionEnabled,
        ejectionCodeId,
        ejectionCodeName,
        endGcode,
      })

      toast.success(ejectionEnabled ? `Ejection set to "${ejectionCodeName}"` : 'Ejection disabled')
    } catch {
      toast.error('Failed to update ejection settings')
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
      updateQuantity.mutate({ id, quantity: quantityValue })
    }
    setEditingQuantity(null)
  }

  const handleQuantityIncrement = (id: number, currentQuantity: number) => {
    updateQuantity.mutate({ id, quantity: currentQuantity + 1 })
  }

  const handleQuantityDecrement = (id: number, currentQuantity: number) => {
    if (currentQuantity > 0) {
      updateQuantity.mutate({ id, quantity: currentQuantity - 1 })
    }
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
    bulkDeleteOrders.mutate(Array.from(selectedIds), {
      onSuccess: (data) => {
        setSelectedIds(new Set())
        toast.success(`${data?.deleted_count ?? selectedIds.size} order(s) deleted`)
      },
      onError: () => {
        toast.error('Failed to delete orders')
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
              onClick={() => handleQuantityDecrement(id, currentQty)}
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
              onClick={() => handleQuantityIncrement(id, currentQty)}
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
        const sent = info.getValue()
        const total = info.row.original.quantity
        return (
          <span className={sent >= total ? 'text-green-600 font-medium' : ''}>
            {sent}/{total}
          </span>
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
              <SelectTrigger className="w-[130px] h-8 text-xs">
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
            {/* Show cooldown temperature indicator if set */}
            {cooldownTemp !== undefined && cooldownTemp !== null && (
              <Badge
                variant="outline"
                className="h-6 px-1.5 text-xs flex items-center gap-0.5 text-cyan-600 border-cyan-300"
                title={`Cooldown: Wait for bed to reach ${cooldownTemp}°C before ejection`}
              >
                <Thermometer className="h-3 w-3" />
                {cooldownTemp}°
              </Badge>
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
                    No items in library.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </DndContext>
      </div>
    </div>
  )
}

export default OrdersTable
