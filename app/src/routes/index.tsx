import { createFileRoute, Link } from '@tanstack/react-router'
import { Download, Loader2, Plus, Upload } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { StatsCards } from '@/components/layout/StatsCards'
import { BulkImportDialog } from '@/components/orders/BulkImportDialog'
import { LibraryTable } from '@/components/orders/LibraryTable'
import { AddToLibraryForm } from '@/components/orders/NewOrderForm'
import { QueueTable } from '@/components/orders/QueueTable'
import { PrinterCard } from '@/components/printers/PrinterCard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useLibrary, usePrinters, useQueue } from '@/hooks'
import { api } from '@/lib/api'

export const Route = createFileRoute('/')({ component: Dashboard })

function Dashboard() {
  const { data: printers, isLoading: printersLoading } = usePrinters()
  const { data: library, isLoading: libraryLoading } = useLibrary()
  const { data: queue, isLoading: queueLoading } = useQueue()
  const [importOpen, setImportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const handleExport = async () => {
    setExporting(true)
    try {
      const { blob, filename } = await api.download('/library/export')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Library exported')
    } catch {
      toast.error('Export failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Monitor and manage your print library</p>
      </div>

      {/* Stats Overview */}
      <StatsCards />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Printers Grid - 2 columns on large screens */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Printers</CardTitle>
            </CardHeader>
            <CardContent>
              {printersLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : printers && printers.length > 0 ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {printers.map((printer) => (
                    <PrinterCard key={printer.name} printer={printer} queueJobs={queue || []} />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center gap-4 py-8 text-muted-foreground">
                  <p>No printers configured.</p>
                  <p className="text-sm">Add a printer to get started.</p>
                  <Button asChild>
                    <Link to="/printers">
                      <Plus className="h-4 w-4" />
                      Add printer
                    </Link>
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Library</CardTitle>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                    <Upload className="h-4 w-4 mr-1" />
                    Import
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleExport}
                    disabled={exporting || library?.length === 0}
                  >
                    <Download className="h-4 w-4 mr-1" />
                    {exporting ? 'Exporting...' : 'Export'}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {libraryLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <LibraryTable items={library || []} />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Print Queue</CardTitle>
            </CardHeader>
            <CardContent>
              {queueLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <QueueTable orders={queue || []} />
              )}
            </CardContent>
          </Card>

          <BulkImportDialog open={importOpen} onOpenChange={setImportOpen} />
        </div>

        <div className="space-y-4">
          <AddToLibraryForm />
        </div>
      </div>
    </div>
  )
}
