import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowRight, Loader2, Plus } from 'lucide-react'
import { useMemo } from 'react'
import { StatsCards } from '@/components/layout/StatsCards'
import { LibraryTable } from '@/components/orders/LibraryTable'
import { QueueTable } from '@/components/orders/QueueTable'
import { PrinterCard } from '@/components/printers/PrinterCard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { useLibrary, usePrinters, useQueue } from '@/hooks'
import { listSearchDefaults } from '@/lib/list-search-params'
import { sortLibraryNewestFirst, sortQueueNewestFirst } from '@/lib/paginated-search'

const PREVIEW_LIMIT = 5

export const Route = createFileRoute('/')({ component: Dashboard })

function Dashboard() {
  const { data: printers, isLoading: printersLoading } = usePrinters()
  const { data: library = [], isLoading: libraryLoading } = useLibrary()
  const { data: queue = [], isLoading: queueLoading } = useQueue()

  const libraryPreview = useMemo(
    () => sortLibraryNewestFirst(library).slice(0, PREVIEW_LIMIT),
    [library]
  )
  const queuePreview = useMemo(() => sortQueueNewestFirst(queue).slice(0, PREVIEW_LIMIT), [queue])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Monitor and manage your print farm</p>
      </div>

      <StatsCards />

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
                <PrinterCard
                  key={printer.name}
                  printer={printer}
                  queueJobs={queue}
                  printers={printers ?? []}
                />
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

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Library</CardTitle>
          </CardHeader>
          <CardContent>
            {libraryLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <LibraryTable
                items={libraryPreview}
                previewMode
                emptyMessage="No library items yet."
              />
            )}
          </CardContent>
          {library.length > 0 && (
            <CardFooter>
              <Button variant="link" className="px-0" asChild>
                <Link to="/library" search={listSearchDefaults}>
                  View all library
                  <ArrowRight className="h-4 w-4 ml-1" />
                </Link>
              </Button>
            </CardFooter>
          )}
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
              <QueueTable
                orders={queuePreview}
                allOrders={queue}
                displayOrders={queuePreview}
                printers={printers ?? []}
                previewMode
                emptyMessage="Queue is empty."
              />
            )}
          </CardContent>
          {queue.length > 0 && (
            <CardFooter>
              <Button variant="link" className="px-0" asChild>
                <Link to="/orders" search={listSearchDefaults}>
                  View all queue
                  <ArrowRight className="h-4 w-4 ml-1" />
                </Link>
              </Button>
            </CardFooter>
          )}
        </Card>
      </div>
    </div>
  )
}
