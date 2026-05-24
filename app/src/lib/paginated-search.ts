import { getQueueJobActivity } from '@/lib/printer-queue-job'
import type { LibraryItem, Printer, QueueJob } from '@/types'

export const DEFAULT_PAGE_SIZE = 30
export const PAGE_SIZE_OPTIONS = [30, 50, 100] as const
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number]

export function normalizeSearchQuery(query: string): string {
  return query.trim().toLowerCase()
}

function newestFirstKey(item: { id: number; created_at?: string }): number {
  if (item.created_at) {
    const t = Date.parse(item.created_at)
    if (!Number.isNaN(t)) return t
  }
  return item.id
}

/** Newest items first (higher id / later created_at). */
export function sortLibraryNewestFirst(items: LibraryItem[]): LibraryItem[] {
  return [...items].sort((a, b) => newestFirstKey(b) - newestFirstKey(a))
}

/** Newest jobs first for display; canonical print priority remains API array order. */
export function sortQueueNewestFirst(jobs: QueueJob[]): QueueJob[] {
  return [...jobs].sort((a, b) => newestFirstKey(b) - newestFirstKey(a))
}

function matchesQuery(haystack: string, query: string): boolean {
  return haystack.toLowerCase().includes(query)
}

export function filterLibraryItems(items: LibraryItem[], query: string): LibraryItem[] {
  const q = normalizeSearchQuery(query)
  if (!q) return items
  return items.filter((item) => {
    const name = item.name ?? ''
    const filename = item.filename ?? ''
    const ejection = item.ejection_code_name ?? ''
    const groups = (item.groups ?? []).map(String).join(' ')
    const searchable = [name, filename, ejection, groups].join(' ')
    return matchesQuery(searchable, q)
  })
}

export function filterQueueJobs(
  jobs: QueueJob[],
  query: string,
  printers: Printer[] = []
): QueueJob[] {
  const q = normalizeSearchQuery(query)
  if (!q) return jobs
  return jobs.filter((job) => {
    const name = job.name ?? ''
    const filename = job.filename ?? ''
    const status = job.status ?? ''
    const activity = getQueueJobActivity(job, printers)
    const progress = [
      `${activity.completed}/${activity.inProgress}/${activity.pending}`,
      `${activity.completed} completed`,
      `${activity.inProgress} in progress`,
      `${activity.pending} pending`,
      `${activity.total} total`,
    ].join(' ')
    const groups = (job.groups ?? []).map(String).join(' ')
    const ejection = job.ejection_code_name ?? ''
    const searchable = [name, filename, status, progress, groups, ejection].join(' ')
    return matchesQuery(searchable, q)
  })
}

export interface PaginateResult<T> {
  pageItems: T[]
  totalCount: number
  totalPages: number
  startIndex: number
  endIndex: number
  page: number
}

export function paginateItems<T>(items: T[], page: number, pageSize: number): PaginateResult<T> {
  const totalCount = items.length
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize) || 1)
  const safePage = Math.min(Math.max(1, page), totalPages)
  const startIndex = totalCount === 0 ? 0 : (safePage - 1) * pageSize
  const endIndex = totalCount === 0 ? 0 : Math.min(startIndex + pageSize, totalCount)
  const pageItems = items.slice(startIndex, endIndex)
  return {
    pageItems,
    totalCount,
    totalPages,
    startIndex,
    endIndex,
    page: safePage,
  }
}

export function parsePageSize(value: unknown): PageSize {
  const n = Number(value)
  if (PAGE_SIZE_OPTIONS.includes(n as PageSize)) return n as PageSize
  return DEFAULT_PAGE_SIZE
}
