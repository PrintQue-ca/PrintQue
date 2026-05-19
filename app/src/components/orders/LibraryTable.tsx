import { ListPlus, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useDeleteLibraryItem } from '@/hooks'
import type { LibraryItem } from '@/types'
import { BulkEnqueueDialog } from './BulkEnqueueDialog'
import { LibraryEditDialog } from './LibraryEditDialog'

interface LibraryTableProps {
  items: LibraryItem[]
}

export function LibraryTable({ items }: LibraryTableProps) {
  const deleteItem = useDeleteLibraryItem()
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [enqueueOpen, setEnqueueOpen] = useState(false)
  const [editItem, setEditItem] = useState<LibraryItem | null>(null)

  const selectedItems = items.filter((i) => selectedIds.has(i.id))

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)))
    }
  }

  const handleDelete = (id: number) => {
    if (!confirm('Delete this library item?')) return
    deleteItem.mutate(id, {
      onSuccess: () => toast.success('Deleted from library'),
      onError: () => toast.error('Failed to delete'),
    })
  }

  return (
    <>
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-2 mb-3">
          <Button size="sm" onClick={() => setEnqueueOpen(true)}>
            <ListPlus className="h-4 w-4 mr-1" />
            Add {selectedIds.size} to queue
          </Button>
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={items.length > 0 && selectedIds.size === items.length}
                onCheckedChange={toggleAll}
              />
            </TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Groups</TableHead>
            <TableHead>Ejection</TableHead>
            <TableHead className="w-28" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                No items in library. Upload a file to get started.
              </TableCell>
            </TableRow>
          ) : (
            items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  <Checkbox
                    checked={selectedIds.has(item.id)}
                    onCheckedChange={() => toggleSelect(item.id)}
                  />
                </TableCell>
                <TableCell>
                  <div>
                    <p className="font-medium">{item.name || item.filename}</p>
                    {item.name && <p className="text-xs text-muted-foreground">{item.filename}</p>}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {(item.groups || ['Default']).map((g) => (
                      <Badge key={String(g)} variant="secondary" className="text-xs">
                        {String(g)}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {item.ejection_enabled ? item.ejection_code_name || 'On' : 'Off'}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setEditItem(item)}
                      title="Edit"
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(item.id)}
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <BulkEnqueueDialog open={enqueueOpen} onOpenChange={setEnqueueOpen} items={selectedItems} />
      <LibraryEditDialog
        item={editItem}
        open={!!editItem}
        onOpenChange={(o) => !o && setEditItem(null)}
      />
    </>
  )
}
