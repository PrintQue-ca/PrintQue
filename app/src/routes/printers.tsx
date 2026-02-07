import { createFileRoute } from '@tanstack/react-router'
import { Eye, EyeOff, Loader2, Plus, Settings, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { EditPrinterDialog } from '@/components/printers/EditPrinterDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { useAddPrinter, useDeletePrinter, usePrinters } from '@/hooks'
import type { Printer, PrinterFormData, PrinterType } from '@/types'

export const Route = createFileRoute('/printers')({ component: PrintersPage })

function PrintersPage() {
  const { data: printers, isLoading } = usePrinters()
  const addPrinter = useAddPrinter()
  const deletePrinter = useDeletePrinter()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingPrinter, setEditingPrinter] = useState<Printer | null>(null)
  const [showAccessCode, setShowAccessCode] = useState(false)
  const [formData, setFormData] = useState<PrinterFormData>({
    name: '',
    ip: '',
    type: 'bambu',
    api_key: '',
    serial_number: '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name || !formData.ip) {
      toast.error('Name and IP address are required')
      return
    }
    if (
      formData.type === 'bambu' &&
      (!formData.serial_number?.trim() || !formData.api_key?.trim())
    ) {
      toast.error('Serial number and access code are required for Bambu printers')
      return
    }

    try {
      await addPrinter.mutateAsync(formData)
      toast.success('Printer added successfully', { duration: 4000 })
      setIsDialogOpen(false)
      setShowAccessCode(false)
      setFormData({ name: '', ip: '', type: 'bambu', api_key: '', serial_number: '' })
    } catch (error) {
      let message = 'Failed to add printer'
      if (error instanceof Error && error.message) {
        try {
          const parsed = JSON.parse(error.message) as { error?: string }
          message = parsed.error ?? error.message
        } catch {
          message = error.message
        }
      }
      toast.error(message)
    }
  }

  const handleDelete = async (name: string) => {
    if (confirm(`Are you sure you want to delete printer "${name}"?`)) {
      try {
        await deletePrinter.mutateAsync(name)
        toast.success('Printer deleted')
      } catch (_error) {
        toast.error('Failed to delete printer')
      }
    }
  }

  const statusColors: Record<string, string> = {
    IDLE: 'bg-green-500',
    PRINTING: 'bg-blue-500',
    FINISHED: 'bg-yellow-500',
    ERROR: 'bg-red-500',
    EJECTING: 'bg-purple-500',
    PAUSED: 'bg-orange-500',
    OFFLINE: 'bg-gray-500',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Printers</h1>
          <p className="text-muted-foreground">Manage your connected printers</p>
        </div>
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Add Printer
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Add New Printer</DialogTitle>
              <DialogDescription>
                Connect a new printer to PrintQue. Fill in the details below.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit}>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">Printer Name</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="My Printer"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="ip">IP Address</Label>
                  <Input
                    id="ip"
                    value={formData.ip}
                    onChange={(e) => setFormData({ ...formData, ip: e.target.value })}
                    placeholder="192.168.1.100"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="type">Printer Type</Label>
                  <Select
                    value={formData.type}
                    onValueChange={(value: PrinterType) =>
                      setFormData({ ...formData, type: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="bambu">Bambu Lab</SelectItem>
                      <SelectItem value="prusa">Prusa</SelectItem>
                      <SelectItem value="octoprint">OctoPrint</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {formData.type === 'bambu' && (
                  <>
                    <div className="grid gap-2">
                      <Label htmlFor="serial">Serial Number</Label>
                      <Input
                        id="serial"
                        value={formData.serial_number}
                        onChange={(e) =>
                          setFormData({ ...formData, serial_number: e.target.value })
                        }
                        placeholder="Serial number"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="api_key">Access Code</Label>
                      <div className="relative">
                        <Input
                          id="api_key"
                          type={showAccessCode ? 'text' : 'password'}
                          value={formData.api_key}
                          onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                          placeholder="Access code from printer"
                          className="pr-9"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                          onClick={() => setShowAccessCode((prev) => !prev)}
                          aria-label={showAccessCode ? 'Hide access code' : 'Show access code'}
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
                {(formData.type === 'prusa' || formData.type === 'octoprint') && (
                  <div className="grid gap-2">
                    <Label htmlFor="api_key">API Key</Label>
                    <Input
                      id="api_key"
                      type="password"
                      value={formData.api_key}
                      onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                      placeholder="API key"
                    />
                  </div>
                )}
              </div>
              <DialogFooter>
                <Button type="submit" disabled={addPrinter.isPending}>
                  {addPrinter.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Adding...
                    </>
                  ) : (
                    'Add Printer'
                  )}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Connected Printers</CardTitle>
          <CardDescription>View and manage all printers connected to PrintQue</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : printers && printers.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>IP Address</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {printers.map((printer) => (
                  <TableRow key={printer.name}>
                    <TableCell className="font-medium">{printer.name}</TableCell>
                    <TableCell>{printer.ip}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize">
                        {printer.type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge className={statusColors[printer.status] || 'bg-gray-500'}>
                        {printer.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {printer.status === 'PRINTING' && printer.progress !== undefined
                        ? `${printer.progress}%`
                        : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingPrinter(printer)}
                          aria-label="Edit printer"
                        >
                          <Settings className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => handleDelete(printer.name)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <p>No printers connected yet.</p>
              <p className="text-sm">Click "Add Printer" to get started.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <EditPrinterDialog
        printer={editingPrinter}
        open={!!editingPrinter}
        onOpenChange={(open) => !open && setEditingPrinter(null)}
      />
    </div>
  )
}
