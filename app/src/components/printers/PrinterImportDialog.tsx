import { Upload } from 'lucide-react'
import { useState } from 'react'
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
import { useImportPrinters } from '@/hooks'

interface PrinterImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PrinterImportDialog({ open, onOpenChange }: PrinterImportDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<{
    success_count: number
    failed_count: number
    failures: Array<{ row: number; error: string }>
  } | null>(null)
  const importPrinters = useImportPrinters()

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setFile(null)
      setResult(null)
    }
    onOpenChange(next)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected?.name.toLowerCase().endsWith('.json')) {
      setFile(selected)
      setResult(null)
    } else if (selected) {
      toast.error('Please select a .json file (from Export)')
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    if (dropped?.name.toLowerCase().endsWith('.json')) {
      setFile(dropped)
      setResult(null)
    } else {
      toast.error('Please drop a .json file (from Export)')
    }
  }

  const handleSubmit = async () => {
    if (!file) {
      toast.error('Select a file first')
      return
    }
    setResult(null)
    try {
      const data = await importPrinters.mutateAsync(file)
      setResult({
        success_count: data.success_count,
        failed_count: data.failed_count,
        failures: data.failures ?? [],
      })
      if (data.success_count > 0) {
        toast.success(`${data.success_count} printer(s) imported`)
      }
      if (data.failed_count > 0) {
        toast.error(`${data.failed_count} row(s) failed`)
      }
      if (data.success_count > 0 && data.failed_count === 0) {
        setFile(null)
      }
    } catch {
      toast.error('Import failed')
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Import printers</DialogTitle>
          <DialogDescription>
            Upload a JSON file from a previous Export. Credentials are stored encrypted; re-import
            on this machine will restore printers without re-entering API keys or access codes.
          </DialogDescription>
        </DialogHeader>
        <div
          className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => document.getElementById('printer-import-file')?.click()}
        >
          <input
            id="printer-import-file"
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleFileChange}
          />
          <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
          {file ? (
            <p className="text-sm font-medium">{file.name}</p>
          ) : (
            <p className="text-sm text-muted-foreground">Drop or click to select .json file</p>
          )}
        </div>
        {result && (
          <div className="rounded-md border bg-muted/50 p-3 text-sm space-y-1">
            <p>
              <strong>Imported:</strong> {result.success_count}
            </p>
            <p>
              <strong>Failed:</strong> {result.failed_count}
            </p>
            {result.failures.length > 0 && (
              <ul className="list-disc pl-4 mt-2 max-h-32 overflow-y-auto">
                {result.failures.slice(0, 10).map((f, i) => (
                  <li key={i}>
                    Row {f.row}: {f.error}
                  </li>
                ))}
                {result.failures.length > 10 && (
                  <li className="text-muted-foreground">
                    … and {result.failures.length - 10} more
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Close
          </Button>
          <Button onClick={handleSubmit} disabled={!file || importPrinters.isPending}>
            {importPrinters.isPending ? 'Importing...' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
