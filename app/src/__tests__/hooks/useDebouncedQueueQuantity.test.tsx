/**
 * Tests for debounced queue quantity updates (lib + hook).
 */

import { QueryClient } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createDebouncedQueueQuantityActions,
  QUANTITY_DEBOUNCE_MS,
} from '../../lib/debounced-queue-quantity'
import type { QueueJob } from '../../types'

const mockJobs: QueueJob[] = [
  {
    id: 1,
    filename: 'part.gcode',
    quantity: 5,
    sent: 2,
    status: 'partial',
    groups: ['Default'],
  },
  {
    id: 2,
    filename: 'other.gcode',
    quantity: 3,
    sent: 3,
    status: 'partial',
    groups: ['Default'],
  },
]

describe('createDebouncedQueueQuantityActions', () => {
  let queryClient: QueryClient
  let patch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    queryClient.setQueryData(['queue'], structuredClone(mockJobs))
    patch = vi.fn()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('updates queue cache optimistically on bumpQuantity', () => {
    const { bumpQuantity } = createDebouncedQueueQuantityActions(queryClient, patch)
    bumpQuantity(1, 1)
    expect(queryClient.getQueryData<QueueJob[]>(['queue'])?.find((j) => j.id === 1)?.quantity).toBe(
      6
    )
    expect(patch).not.toHaveBeenCalled()
  })

  it('sends a single PATCH after debounce when bumped rapidly', () => {
    const { bumpQuantity } = createDebouncedQueueQuantityActions(queryClient, patch)
    bumpQuantity(1, 1)
    bumpQuantity(1, 1)
    bumpQuantity(1, 1)
    expect(queryClient.getQueryData<QueueJob[]>(['queue'])?.find((j) => j.id === 1)?.quantity).toBe(
      8
    )
    vi.advanceTimersByTime(QUANTITY_DEBOUNCE_MS)
    expect(patch).toHaveBeenCalledTimes(1)
    expect(patch).toHaveBeenCalledWith({ id: 1, quantity: 8 })
  })

  it('flushQuantity PATCHes immediately without waiting for debounce', () => {
    const { bumpQuantity, flushQuantity } = createDebouncedQueueQuantityActions(queryClient, patch)
    bumpQuantity(1, 1)
    flushQuantity(1)
    expect(patch).toHaveBeenCalledTimes(1)
    expect(patch).toHaveBeenCalledWith({ id: 1, quantity: 6 })
    vi.advanceTimersByTime(QUANTITY_DEBOUNCE_MS)
    expect(patch).toHaveBeenCalledTimes(1)
  })

  it('does not decrement quantity below sent', () => {
    const { bumpQuantity } = createDebouncedQueueQuantityActions(queryClient, patch)
    bumpQuantity(2, -1)
    expect(queryClient.getQueryData<QueueJob[]>(['queue'])?.find((j) => j.id === 2)?.quantity).toBe(
      3
    )
    expect(patch).not.toHaveBeenCalled()
  })

  it('invokes patch after debounce so the hook can handle errors', async () => {
    const failingPatch = vi.fn().mockRejectedValue(new Error('server error'))
    const { bumpQuantity } = createDebouncedQueueQuantityActions(queryClient, failingPatch)

    bumpQuantity(1, 1)
    vi.advanceTimersByTime(QUANTITY_DEBOUNCE_MS)

    await vi.waitFor(() => {
      expect(failingPatch).toHaveBeenCalledWith({ id: 1, quantity: 6 })
    })
  })
})
