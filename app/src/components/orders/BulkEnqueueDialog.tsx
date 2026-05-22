import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBulkEnqueue } from '@/hooks'
import type { LibraryItem } from '@/types'

interface BulkEnqueueDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  items: LibraryItem[]
}

export function BulkEnqueueDialog({ open, onOpenChange, items }: BulkEnqueueDialogProps) {
  const bulkEnqueue = useBulkEnqueue()
  const [quantities, setQuantities] = useState<Record<number, number>>({})
  const [applyAllQty, setApplyAllQty] = useState('1')

  useEffect(() => {
    if (open) {
      const initial: Record<number, number> = {}
      for (const item of items) {
        initial[item.id] = 1
      }
      setQuantities(initial)
      setApplyAllQty('1')
    }
  }, [open, items])

  const handleApplyAll = () => {
    const q = Math.max(1, parseInt(applyAllQty, 10) || 1)
    const next: Record<number, number> = {}
    for (const item of items) {
      next[item.id] = q
    }
    setQuantities(next)
  }

  const handleSubmit = async () => {
    const payload = items.map((item) => ({
      library_item_id: item.id,
      quantity: Math.max(1, quantities[item.id] ?? 1),
    }))
    try {
      const result = await bulkEnqueue.mutateAsync(payload)
      toast.success(`Enqueued ${result.count} job(s)`)
      onOpenChange(false)
    } catch {
      toast.error('Failed to enqueue jobs')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Add to print queue</DialogTitle>
          <DialogDescription>
            Set how many copies to print for each selected library item.
          </DialogDescription>
        </DialogHeader>

        {items.length > 1 && (
          <div className="flex items-end gap-2 py-2 border-b">
            <div className="space-y-1 flex-1">
              <Label htmlFor="apply-all-qty">Quantity for all</Label>
              <Input
                id="apply-all-qty"
                type="number"
                min={1}
                value={applyAllQty}
                onChange={(e) => setApplyAllQty(e.target.value)}
              />
            </div>
            <Button type="button" variant="secondary" onClick={handleApplyAll}>
              Apply to all
            </Button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-3 py-2 min-h-0">
          {items.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{item.name || item.filename}</p>
                <p className="text-xs text-muted-foreground truncate">{item.filename}</p>
              </div>
              <Input
                type="number"
                min={1}
                className="w-20"
                value={quantities[item.id] ?? 1}
                onChange={(e) =>
                  setQuantities((prev) => ({
                    ...prev,
                    [item.id]: Math.max(1, parseInt(e.target.value, 10) || 1),
                  }))
                }
              />
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={bulkEnqueue.isPending || items.length === 0}
          >
            {bulkEnqueue.isPending ? 'Enqueueing...' : `Enqueue ${items.length} item(s)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
