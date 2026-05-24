import { DEFAULT_PAGE_SIZE, type PageSize, parsePageSize } from '@/lib/paginated-search'

export interface ListSearchParams {
  q: string
  page: number
  pageSize: PageSize
}

export const listSearchDefaults: ListSearchParams = {
  q: '',
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
}

export function validateListSearch(search: Record<string, unknown>): ListSearchParams {
  const page = Math.max(1, Number(search.page) || 1)
  const pageSize = parsePageSize(search.pageSize)
  const q = typeof search.q === 'string' ? search.q : ''
  return { q, page, pageSize }
}
