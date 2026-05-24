import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '@/lib/paginated-search'

interface TablePaginationProps {
  query: string
  onQueryChange: (value: string) => void
  page: number
  onPageChange: (page: number) => void
  pageSize: number
  onPageSizeChange: (size: 30 | 50 | 100) => void
  totalCount: number
  totalPages: number
  startIndex: number
  endIndex: number
  searchPlaceholder?: string
}

export function TablePagination({
  query,
  onQueryChange,
  page,
  onPageChange,
  pageSize,
  onPageSizeChange,
  totalCount,
  totalPages,
  startIndex,
  endIndex,
  searchPlaceholder = 'Search…',
}: TablePaginationProps) {
  const showingFrom = totalCount === 0 ? 0 : startIndex + 1
  const showingTo = endIndex

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative flex-1 max-w-md">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          type="search"
          placeholder={searchPlaceholder}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          className="pl-8"
          aria-label="Search"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground whitespace-nowrap">
          {totalCount === 0 ? 'No results' : `Showing ${showingFrom}–${showingTo} of ${totalCount}`}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Per page</span>
          <Select
            value={String(pageSize)}
            onValueChange={(v) => onPageSizeChange(Number(v) as 30 | 50 | 100)}
          >
            <SelectTrigger className="w-[72px] h-8" aria-label="Items per page">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZE_OPTIONS.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground min-w-[4rem] text-center">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

export { DEFAULT_PAGE_SIZE }
