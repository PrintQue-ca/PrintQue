import { useMemo } from 'react'
import { type PageSize, paginateItems } from '@/lib/paginated-search'

export interface UsePaginatedSearchOptions<T> {
  items: T[]
  query: string
  page: number
  pageSize: PageSize
  filterFn: (items: T[], query: string) => T[]
}

export function usePaginatedSearch<T>({
  items,
  query,
  page,
  pageSize,
  filterFn,
}: UsePaginatedSearchOptions<T>) {
  const filtered = useMemo(() => filterFn(items, query), [items, query, filterFn])

  const pagination = useMemo(
    () => paginateItems(filtered, page, pageSize),
    [filtered, page, pageSize]
  )

  return {
    filtered,
    ...pagination,
  }
}

export { DEFAULT_PAGE_SIZE } from '@/lib/paginated-search'
