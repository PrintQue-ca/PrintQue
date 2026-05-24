import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PAGE_SIZE,
  filterLibraryItems,
  filterQueueJobs,
  PAGE_SIZE_OPTIONS,
  paginateItems,
  parsePageSize,
  sortLibraryNewestFirst,
  sortQueueNewestFirst,
} from '@/lib/paginated-search'
import type { LibraryItem, Printer, QueueJob } from '@/types'

const libraryItems: LibraryItem[] = [
  {
    id: 1,
    filename: 'widget.gcode',
    name: 'Widget',
    groups: ['Alpha'],
    ejection_code_name: 'Push',
  },
  {
    id: 2,
    filename: 'bracket.gcode',
    groups: ['Beta'],
  },
]

const queueJobs: QueueJob[] = [
  {
    id: 10,
    library_item_id: 1,
    filename: 'widget.gcode',
    name: 'Widget',
    quantity: 10,
    sent: 3,
    status: 'partial',
    groups: ['Alpha'],
  },
  {
    id: 11,
    library_item_id: 2,
    filename: 'bracket.gcode',
    quantity: 1,
    sent: 0,
    status: 'pending',
    groups: ['Beta'],
  },
]

describe('filterLibraryItems', () => {
  it('returns all items when query is empty', () => {
    expect(filterLibraryItems(libraryItems, '')).toHaveLength(2)
  })

  it('matches name, filename, groups, and ejection', () => {
    expect(filterLibraryItems(libraryItems, 'widget')).toHaveLength(1)
    expect(filterLibraryItems(libraryItems, 'bracket.gcode')[0].id).toBe(2)
    expect(filterLibraryItems(libraryItems, 'alpha')).toHaveLength(1)
    expect(filterLibraryItems(libraryItems, 'push')).toHaveLength(1)
  })
})

describe('filterQueueJobs', () => {
  it('matches status and activity progress', () => {
    expect(filterQueueJobs(queueJobs, 'partial')).toHaveLength(1)
    expect(filterQueueJobs(queueJobs, '3 completed')).toHaveLength(1)
    expect(filterQueueJobs(queueJobs, 'beta')).toHaveLength(1)
  })

  it('matches in progress count from printers', () => {
    const printers: Printer[] = [
      {
        name: 'P1',
        ip: '1.1.1.1',
        type: 'bambu',
        status: 'PRINTING',
        order_id: 10,
      },
      {
        name: 'P2',
        ip: '1.1.1.2',
        type: 'bambu',
        status: 'COOLING',
        order_id: 10,
      },
    ]
    expect(filterQueueJobs(queueJobs, '2 in progress', printers)).toHaveLength(1)
  })
})

describe('paginateItems', () => {
  it('returns empty page for empty list', () => {
    const result = paginateItems([], 1, 30)
    expect(result.pageItems).toEqual([])
    expect(result.totalCount).toBe(0)
    expect(result.totalPages).toBe(1)
    expect(result.startIndex).toBe(0)
    expect(result.endIndex).toBe(0)
  })

  it('paginates with correct bounds on partial last page', () => {
    const items = Array.from({ length: 35 }, (_, i) => i)
    const result = paginateItems(items, 2, 30)
    expect(result.pageItems).toEqual([30, 31, 32, 33, 34])
    expect(result.totalPages).toBe(2)
    expect(result.startIndex).toBe(30)
    expect(result.endIndex).toBe(35)
  })

  it('clamps page to valid range', () => {
    const items = [1, 2, 3]
    expect(paginateItems(items, 99, 30).page).toBe(1)
  })
})

describe('sort newest first', () => {
  it('sorts library by id descending', () => {
    const sorted = sortLibraryNewestFirst(libraryItems)
    expect(sorted.map((i) => i.id)).toEqual([2, 1])
  })

  it('sorts queue by id descending', () => {
    const sorted = sortQueueNewestFirst(queueJobs)
    expect(sorted.map((j) => j.id)).toEqual([11, 10])
  })
})

describe('page size constants', () => {
  it('defaults to 30 and allows up to 100', () => {
    expect(DEFAULT_PAGE_SIZE).toBe(30)
    expect(PAGE_SIZE_OPTIONS).toContain(30)
    expect(PAGE_SIZE_OPTIONS).toContain(100)
    expect(parsePageSize(100)).toBe(100)
    expect(parsePageSize('invalid')).toBe(30)
  })
})
