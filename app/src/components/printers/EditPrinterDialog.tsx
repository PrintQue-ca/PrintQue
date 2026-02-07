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
import { useUpdatePrinter } from '@/hooks'
import type { Printer } from '@/types'

interface EditPrinterDialogProps {
  printer: Printer | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditPrinterDialog({ printer, open, onOpenChange }: EditPrinterDialogProps) {
  const updatePrinter = useUpdatePrinter()
  const [name, setName] = useState('')
  const [group, setGroup] = useState('')

  useEffect(() => {
    if (printer) {
      setName(printer.name)
      setGroup(printer.group ?? 'Default')
    }
  }, [printer])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!printer) return
    if (!name.trim()) {
      toast.error('Name is required')
      return
    }
    try {
      await updatePrinter.mutateAsync({
        name: printer.name,
        data: { name: name.trim(), group: group.trim() || 'Default' },
      })
      toast.success('Printer updated')
      onOpenChange(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update printer'
      toast.error(message)
    }
  }

  if (!printer) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Edit Printer</DialogTitle>
          <DialogDescription>
            Update name and group for {printer.name}. IP and type cannot be changed here.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-name">Printer Name</Label>
              <Input
                id="edit-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Printer"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-group">Group</Label>
              <Input
                id="edit-group"
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                placeholder="Default"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={updatePrinter.isPending}>
              {updatePrinter.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
