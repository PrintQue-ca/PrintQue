import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Download, Loader2, Upload } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { BulkImportDialog } from '@/components/orders/BulkImportDialog'
import { LibraryTable } from '@/components/orders/LibraryTable'
import { AddToLibraryForm } from '@/components/orders/NewOrderForm'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TablePagination } from '@/components/ui/table-pagination'
import { useLibrary, usePaginatedSearch } from '@/hooks'
import { api } from '@/lib/api'
import { validateListSearch } from '@/lib/list-search-params'
import { filterLibraryItems, sortLibraryNewestFirst } from '@/lib/paginated-search'

export const Route = createFileRoute('/library')({
  validateSearch: validateListSearch,
  component: LibraryPage,
})

function LibraryPage() {
  const navigate = useNavigate({ from: Route.fullPath })
  const search = Route.useSearch()
  const { data: library = [], isLoading } = useLibrary()
  const [importOpen, setImportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const librarySorted = useMemo(() => sortLibraryNewestFirst(library), [library])

  const { pageItems, totalCount, totalPages, startIndex, endIndex } = usePaginatedSearch({
    items: librarySorted,
    query: search.q,
    page: search.page,
    pageSize: search.pageSize,
    filterFn: filterLibraryItems,
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
        <h1 className="text-3xl font-bold tracking-tight">Library</h1>
        <p className="text-muted-foreground">Manage print files and enqueue jobs</p>
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
        searchPlaceholder="Search library…"
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Catalog</CardTitle>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                    <Upload className="h-4 w-4 mr-1" />
                    Import
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleExport}
                    disabled={exporting || library.length === 0}
                  >
                    <Download className="h-4 w-4 mr-1" />
                    {exporting ? 'Exporting...' : 'Export'}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <LibraryTable
                  items={pageItems}
                  emptyMessage={
                    search.q
                      ? 'No library items match your search.'
                      : 'No items in library. Upload a file to get started.'
                  }
                />
              )}
            </CardContent>
          </Card>
        </div>

        <div>
          <AddToLibraryForm />
        </div>
      </div>

      <BulkImportDialog open={importOpen} onOpenChange={setImportOpen} />
    </div>
  )
}
