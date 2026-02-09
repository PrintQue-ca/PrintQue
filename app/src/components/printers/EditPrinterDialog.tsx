import { Eye, EyeOff } from 'lucide-react'
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
  const [ip, setIp] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [deviceId, setDeviceId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [showAccessCode, setShowAccessCode] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)

  useEffect(() => {
    if (printer) {
      setName(printer.name)
      setGroup(printer.group ?? 'Default')
      setIp(printer.ip ?? '')
      setDeviceId(printer.serial_number ?? '')
      // Don't pre-fill secrets — show empty so user can enter a new value
      setAccessCode('')
      setApiKey('')
      setShowAccessCode(false)
      setShowApiKey(false)
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
      const data: Record<string, unknown> = {
        name: name.trim(),
        group: group.trim() || 'Default',
      }
      if (ip.trim()) data.ip = ip.trim()
      if (printer.type === 'bambu') {
        if (accessCode.trim()) data.access_code = accessCode.trim()
        if (deviceId.trim()) data.device_id = deviceId.trim()
      } else if (apiKey.trim()) {
        data.api_key = apiKey.trim()
      }
      await updatePrinter.mutateAsync({ name: printer.name, data })
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
          <DialogDescription>Update settings for {printer.name}.</DialogDescription>
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
            <div className="grid gap-2">
              <Label htmlFor="edit-ip">IP Address</Label>
              <Input
                id="edit-ip"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="192.168.1.100"
              />
            </div>
            {printer.type === 'bambu' && (
              <>
                <p className="text-sm text-muted-foreground">
                  You can find the IP address and access code on the printer under Settings → LAN
                  mode.
                </p>
                <div className="grid gap-2">
                  <Label htmlFor="edit-device-id">Serial Number / Device ID</Label>
                  <Input
                    id="edit-device-id"
                    value={deviceId}
                    onChange={(e) => setDeviceId(e.target.value)}
                    placeholder="Leave blank to keep current"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="edit-access-code">Access Code</Label>
                  <div className="relative">
                    <Input
                      id="edit-access-code"
                      type={showAccessCode ? 'text' : 'password'}
                      value={accessCode}
                      onChange={(e) => setAccessCode(e.target.value)}
                      placeholder="Leave blank to keep current"
                      className="pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                      onClick={() => setShowAccessCode(!showAccessCode)}
                      tabIndex={-1}
                    >
                      {showAccessCode ? (
                        <EyeOff className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <Eye className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                  </div>
                </div>
              </>
            )}
            {printer.type === 'prusa' && (
              <div className="grid gap-2">
                <Label htmlFor="edit-api-key">API Key</Label>
                <div className="relative">
                  <Input
                    id="edit-api-key"
                    type={showApiKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Leave blank to keep current"
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                    onClick={() => setShowApiKey(!showApiKey)}
                    tabIndex={-1}
                  >
                    {showApiKey ? (
                      <EyeOff className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <Eye className="h-4 w-4 text-muted-foreground" />
                    )}
                  </Button>
                </div>
              </div>
            )}
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
