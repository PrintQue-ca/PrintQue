import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'
import { useCallback, useMemo } from 'react'
import { QueueTable } from '@/components/orders/QueueTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TablePagination } from '@/components/ui/table-pagination'
import { usePaginatedSearch, usePrinters, useQueue } from '@/hooks'
import { validateListSearch } from '@/lib/list-search-params'
import { filterQueueJobs, sortQueueNewestFirst } from '@/lib/paginated-search'
import type { QueueJob } from '@/types'

export const Route = createFileRoute('/orders')({
  validateSearch: validateListSearch,
  component: OrdersPage,
})

function OrdersPage() {
  const navigate = useNavigate({ from: Route.fullPath })
  const search = Route.useSearch()
  const { data: queue = [], isLoading } = useQueue()
  const { data: printers = [] } = usePrinters()

  const queueSorted = useMemo(() => sortQueueNewestFirst(queue), [queue])

  const filterQueue = useCallback(
    (jobs: QueueJob[], q: string) => filterQueueJobs(jobs, q, printers),
    [printers]
  )

  const { filtered, pageItems, totalCount, totalPages, startIndex, endIndex } = usePaginatedSearch({
    items: queueSorted,
    query: search.q,
    page: search.page,
    pageSize: search.pageSize,
    filterFn: filterQueue,
  })

  const updateSearch = useCallback(
    (updates: Partial<typeof search>) => {
      const next = { ...search, ...updates }
      if (updates.q !== undefined || updates.pageSize !== undefined) {
        next.page = 1
      }
      navigate({ search: next })
    },
    [navigate, search]
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Print Queue</h1>
        <p className="text-muted-foreground">
          Reorder jobs, adjust quantities, and manage ejection
        </p>
      </div>

      <TablePagination
        query={search.q}
        onQueryChange={(q) => updateSearch({ q })}
        page={search.page}
        onPageChange={(page) => updateSearch({ page })}
        pageSize={search.pageSize}
        onPageSizeChange={(pageSize) => updateSearch({ pageSize })}
        totalCount={totalCount}
        totalPages={totalPages}
        startIndex={startIndex}
        endIndex={endIndex}
        searchPlaceholder="Search queue…"
      />

      <Card>
        <CardHeader>
          <CardTitle>Queue</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <QueueTable
              orders={pageItems}
              allOrders={queue}
              displayOrders={filtered}
              printers={printers}
              emptyMessage={search.q ? 'No queue jobs match your search.' : 'No items in queue.'}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
