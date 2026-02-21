import { Upload } from 'lucide-react'
import { useCallback, useState } from 'react'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useImportOrders } from '@/hooks'

interface BulkImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function BulkImportDialog({ open, onOpenChange }: BulkImportDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<{
    success_count: number
    failed_count: number
    failures: Array<{ row: number; error: string }>
  } | null>(null)
  const importOrders = useImportOrders()

  const reset = useCallback(() => {
    setFile(null)
    setResult(null)
  }, [])

  const handleOpenChange = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) {
      setFile(selected)
      setResult(null)
    }
  }

  const handleDrop = (e: React.DragEvent, accept: string) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    if (!dropped) return
    const ext = dropped.name.toLowerCase().slice(-5)
    const ok =
      (accept === 'json' &&
        (ext.endsWith('.json') || dropped.name.toLowerCase().endsWith('.json'))) ||
      (accept === 'csv' && (ext.endsWith('.csv') || dropped.name.toLowerCase().endsWith('.csv')))
    if (ok) {
      setFile(dropped)
      setResult(null)
    } else {
      toast.error(accept === 'json' ? 'Please drop a .json file' : 'Please drop a .csv file')
    }
  }

  const handleDragOver = (e: React.DragEvent) => e.preventDefault()

  const handleSubmit = async () => {
    if (!file) {
      toast.error('Select a file first')
      return
    }
    setResult(null)
    try {
      const data = await importOrders.mutateAsync(file)
      setResult({
        success_count: data.success_count,
        failed_count: data.failed_count,
        failures: data.failures ?? [],
      })
      if (data.success_count > 0) {
        toast.success(`${data.success_count} order(s) imported`)
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

  const acceptJson = '.json'
  const acceptCsv = '.csv'

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Bulk import orders</DialogTitle>
          <DialogDescription>
            Import from a JSON export (re-import) or a CSV file with columns: folder_path, filename,
            quantity, printer_groups.
          </DialogDescription>
        </DialogHeader>
        <Tabs
          defaultValue="json"
          className="w-full"
          onValueChange={() => {
            setFile(null)
            setResult(null)
          }}
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="json">Import JSON</TabsTrigger>
            <TabsTrigger value="csv">Import CSV</TabsTrigger>
          </TabsList>
          <TabsContent value="json" className="space-y-4">
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onDrop={(e) => handleDrop(e, 'json')}
              onDragOver={handleDragOver}
              onClick={() => document.getElementById('bulk-import-json')?.click()}
            >
              <input
                id="bulk-import-json"
                type="file"
                accept={acceptJson}
                className="hidden"
                onChange={handleFileChange}
              />
              <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
              {file?.name.toLowerCase().endsWith('.json') ? (
                <p className="text-sm font-medium">{file.name}</p>
              ) : (
                <p className="text-sm text-muted-foreground">Drop or click to select .json file</p>
              )}
            </div>
          </TabsContent>
          <TabsContent value="csv" className="space-y-4">
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onDrop={(e) => handleDrop(e, 'csv')}
              onDragOver={handleDragOver}
              onClick={() => document.getElementById('bulk-import-csv')?.click()}
            >
              <input
                id="bulk-import-csv"
                type="file"
                accept={acceptCsv}
                className="hidden"
                onChange={handleFileChange}
              />
              <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
              {file?.name.toLowerCase().endsWith('.csv') ? (
                <p className="text-sm font-medium">{file.name}</p>
              ) : (
                <p className="text-sm text-muted-foreground">Drop or click to select .csv file</p>
              )}
            </div>
          </TabsContent>
        </Tabs>
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
          <Button onClick={handleSubmit} disabled={!file || importOrders.isPending}>
            {importOrders.isPending ? 'Importing...' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
