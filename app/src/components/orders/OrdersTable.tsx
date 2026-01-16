import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { ChevronUp, ChevronDown, Trash2, Plus, Minus } from 'lucide-react'
import type { Order } from '@/types'
import { useDeleteOrder, useMoveOrder, useUpdateQuantity } from '@/hooks'
import { useState } from 'react'

interface OrdersTableProps {
  orders: Order[]
}

const columnHelper = createColumnHelper<Order>()

export function OrdersTable({ orders }: OrdersTableProps) {
  const deleteOrder = useDeleteOrder()
  const moveOrder = useMoveOrder()
  const updateQuantity = useUpdateQuantity()
  const [editingQuantity, setEditingQuantity] = useState<number | null>(null)
  const [quantityValue, setQuantityValue] = useState<number>(0)

  const handleDelete = (id: number) => {
    if (confirm('Are you sure you want to delete this order?')) {
      deleteOrder.mutate(id)
    }
  }

  const handleMoveUp = (id: number) => moveOrder.mutate({ id, direction: 'up' })
  const handleMoveDown = (id: number) => moveOrder.mutate({ id, direction: 'down' })

  const handleQuantityChange = (id: number, currentQuantity: number) => {
    setEditingQuantity(id)
    setQuantityValue(currentQuantity)
  }

  const handleQuantitySubmit = (id: number) => {
    if (quantityValue > 0) {
      updateQuantity.mutate({ id, quantity: quantityValue })
    }
    setEditingQuantity(null)
  }

  const handleQuantityIncrement = (id: number, currentQuantity: number) => {
    updateQuantity.mutate({ id, quantity: currentQuantity + 1 })
  }

  const handleQuantityDecrement = (id: number, currentQuantity: number) => {
    if (currentQuantity > 1) {
      updateQuantity.mutate({ id, quantity: currentQuantity - 1 })
    }
  }

  const columns = [
    columnHelper.accessor('priority', {
      header: '#',
      cell: (info) => (
        <div className="flex items-center gap-1">
          <span className="font-medium">{info.getValue()}</span>
          <div className="flex flex-col">
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0"
              onClick={() => handleMoveUp(info.row.original.id)}
            >
              <ChevronUp className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0"
              onClick={() => handleMoveDown(info.row.original.id)}
            >
              <ChevronDown className="h-3 w-3" />
            </Button>
          </div>
        </div>
      ),
    }),
    columnHelper.accessor('filename', {
      header: 'File',
      cell: (info) => (
        <span className="truncate max-w-[200px] block" title={info.getValue()}>
          {info.getValue()}
        </span>
      ),
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
              min={1}
              value={quantityValue}
              onChange={(e) => setQuantityValue(parseInt(e.target.value) || 1)}
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
        if (!groups || groups.length === 0) return <span className="text-muted-foreground">All</span>
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
    data: orders,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
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
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center">
                No items in library.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

export default OrdersTable
