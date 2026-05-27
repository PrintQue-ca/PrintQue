import { FileUp } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
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
import {
  useEjectionCodes,
  useGroups,
  useReplaceLibraryFile,
  useUpdateLibraryEjection,
  useUpdateLibraryItem,
} from '@/hooks'
import { parseApiErrorMessage } from '@/lib/api'
import type { LibraryItem } from '@/types'

interface LibraryEditDialogProps {
  item: LibraryItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function LibraryEditDialog({ item, open, onOpenChange }: LibraryEditDialogProps) {
  const { data: groups } = useGroups()
  const { data: ejectionCodes } = useEjectionCodes()
  const updateItem = useUpdateLibraryItem()
  const updateEjection = useUpdateLibraryEjection()
  const replaceFile = useReplaceLibraryFile()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState('')
  const [selectedGroup, setSelectedGroup] = useState<string>('all')
  const [ejectionEnabled, setEjectionEnabled] = useState(false)
  const [ejectionCodeId, setEjectionCodeId] = useState<string>('none')
  const [endGcode, setEndGcode] = useState('')
  const [cooldownTemp, setCooldownTemp] = useState('')

  useEffect(() => {
    if (!item || !open) return
    setName(item.name ?? '')
    const g = item.groups?.[0]
    setSelectedGroup(g !== undefined && g !== null ? String(g) : 'all')
    setEjectionEnabled(!!item.ejection_enabled)
    setEjectionCodeId(item.ejection_code_id ?? 'none')
    const preset = ejectionCodes?.find((c) => c.id === item.ejection_code_id)
    setEndGcode(preset?.gcode ?? '')
    setCooldownTemp(
      item.cooldown_temp === undefined || item.cooldown_temp === null
        ? ''
        : String(item.cooldown_temp)
    )
  }, [item, open, ejectionCodes])

  const handleSave = async () => {
    if (!item) return
    try {
      const groupsPayload =
        selectedGroup === 'all' ? ['Default'] : [sanitizeGroupValue(selectedGroup)]
      await updateItem.mutateAsync({
        id: item.id,
        data: { name: name.trim() || undefined, groups: groupsPayload },
      })
      const body: Parameters<typeof updateEjection.mutateAsync>[0] = {
        id: item.id,
        ejectionEnabled,
      }
      if (ejectionEnabled) {
        if (ejectionCodeId !== 'custom' && ejectionCodeId !== 'none') {
          body.ejectionCodeId = ejectionCodeId
        } else if (endGcode.trim()) {
          body.endGcode = endGcode
        }
        const ct = cooldownTemp.trim()
        if (ct) {
          const parsed = parseInt(ct, 10)
          if (!Number.isNaN(parsed) && parsed >= 0 && parsed <= 100) {
            body.cooldownTemp = parsed
          }
        } else {
          body.cooldownTemp = null
        }
      } else {
        body.ejectionCodeId = null
      }
      await updateEjection.mutateAsync(body)
      toast.success('Library item updated')
      onOpenChange(false)
    } catch {
      toast.error('Failed to update library item')
    }
  }

  const handleReplaceFile = async (file: File) => {
    if (!item) return
    try {
      await replaceFile.mutateAsync({ id: item.id, file })
      toast.success('Print file replaced')
    } catch (e) {
      toast.error(parseApiErrorMessage(e, 'Failed to replace file'))
    }
  }

  if (!item) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit library item</DialogTitle>
          <DialogDescription>
            Update metadata or replace the print file. File replacement is blocked while prints are
            active for this item.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>

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

          <div className="space-y-2">
            <Label>Print file</Label>
            <p className="text-sm text-muted-foreground">{item.filename}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={replaceFile.isPending}
            >
              <FileUp className="h-4 w-4 mr-1" />
              Replace file
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".gcode,.3mf,.stl"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void handleReplaceFile(f)
                e.target.value = ''
              }}
            />
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
          <Button
            onClick={() => void handleSave()}
            disabled={updateItem.isPending || updateEjection.isPending}
          >
            Save changes
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
