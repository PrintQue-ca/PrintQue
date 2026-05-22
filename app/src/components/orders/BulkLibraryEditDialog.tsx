import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useBulkUpdateLibrary, useEjectionCodes, useGroups } from '@/hooks'
import type { LibraryItem } from '@/types'

interface BulkLibraryEditDialogProps {
  items: LibraryItem[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export function BulkLibraryEditDialog({
  items,
  open,
  onOpenChange,
  onSuccess,
}: BulkLibraryEditDialogProps) {
  const { data: groups } = useGroups()
  const { data: ejectionCodes } = useEjectionCodes()
  const bulkUpdate = useBulkUpdateLibrary()

  const [selectedGroup, setSelectedGroup] = useState<string>('all')
  const [ejectionEnabled, setEjectionEnabled] = useState(false)
  const [ejectionCodeId, setEjectionCodeId] = useState<string>('none')
  const [endGcode, setEndGcode] = useState('')
  const [cooldownTemp, setCooldownTemp] = useState('')

  useEffect(() => {
    if (!open || items.length === 0) return
    setSelectedGroup('all')
    setEjectionEnabled(false)
    setEjectionCodeId('none')
    setEndGcode('')
    setCooldownTemp('')
  }, [open, items.length])

  const handleSave = async () => {
    if (items.length === 0) return
    const groupsPayload =
      selectedGroup === 'all' ? ['Default'] : [sanitizeGroupValue(selectedGroup)]

    const payload: Parameters<typeof bulkUpdate.mutateAsync>[0] = {
      ids: items.map((i) => i.id),
      groups: groupsPayload,
      ejectionEnabled,
    }

    if (ejectionEnabled) {
      if (ejectionCodeId !== 'custom' && ejectionCodeId !== 'none') {
        payload.ejectionCodeId = ejectionCodeId
      } else if (endGcode.trim()) {
        payload.endGcode = endGcode
      }
      const ct = cooldownTemp.trim()
      if (ct) {
        const parsed = parseInt(ct, 10)
        if (!Number.isNaN(parsed) && parsed >= 0 && parsed <= 100) {
          payload.cooldownTemp = parsed
        }
      } else {
        payload.cooldownTemp = null
      }
    } else {
      payload.ejectionCodeId = null
    }

    try {
      await bulkUpdate.mutateAsync(payload)
      onOpenChange(false)
      onSuccess?.()
    } catch {
      // toast handled in hook
    }
  }

  const count = items.length

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit {count} library items</DialogTitle>
          <DialogDescription>
            Changes apply to all selected items. Display names and print files are not changed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Printer group</Label>
            <Select value={selectedGroup} onValueChange={setSelectedGroup}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Default</SelectItem>
                {groups?.map((g) => (
                  <SelectItem key={g.id} value={g.id.toString()}>
                    {g.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Switch checked={ejectionEnabled} onCheckedChange={setEjectionEnabled} />
            <Label>Auto-ejection</Label>
          </div>

          {ejectionEnabled && (
            <>
              <div className="space-y-2">
                <Label>Ejection preset</Label>
                <Select value={ejectionCodeId} onValueChange={setEjectionCodeId}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Off</SelectItem>
                    <SelectItem value="custom">Custom G-code</SelectItem>
                    {ejectionCodes?.map((code) => (
                      <SelectItem key={code.id} value={code.id}>
                        {code.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {ejectionCodeId === 'custom' && (
                <GcodeEditor value={endGcode} onChange={setEndGcode} className="min-h-[120px]" />
              )}
              <div className="space-y-2">
                <Label>Cooldown temp (°C, Bambu)</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={cooldownTemp}
                  onChange={(e) => setCooldownTemp(e.target.value)}
                  placeholder="Optional"
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void handleSave()} disabled={bulkUpdate.isPending || count === 0}>
            Apply to {count} items
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function sanitizeGroupValue(value: string): number | string {
  const n = parseInt(value, 10)
  return Number.isNaN(n) ? value : n
}
