import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { optimisticRemoveQueueJobs, restoreQueueCache } from '../../lib/optimistic-queue-cache'
import type { QueueJob } from '../../types'

const mockJobs: QueueJob[] = [
  { id: 1, filename: 'a.gcode', quantity: 1, sent: 0, status: 'pending', groups: [] },
  { id: 2, filename: 'b.gcode', quantity: 2, sent: 1, status: 'partial', groups: [] },
  { id: 3, filename: 'c.gcode', quantity: 1, sent: 0, status: 'pending', groups: [] },
]

describe('optimisticRemoveQueueJobs', () => {
  it('removes a single job from the queue cache', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['queue'], [...mockJobs])

    await optimisticRemoveQueueJobs(queryClient, 2)

    const queue = queryClient.getQueryData<QueueJob[]>(['queue'])
    expect(queue?.map((j) => j.id)).toEqual([1, 3])
  })

  it('removes multiple jobs from the queue cache', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['queue'], [...mockJobs])

    await optimisticRemoveQueueJobs(queryClient, [1, 3])

    expect(queryClient.getQueryData<QueueJob[]>(['queue'])?.map((j) => j.id)).toEqual([2])
  })

  it('restoreQueueCache rolls back a failed delete', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['queue'], [...mockJobs])

    const { previous } = await optimisticRemoveQueueJobs(queryClient, 2)
    restoreQueueCache(queryClient, previous)

    expect(queryClient.getQueryData<QueueJob[]>(['queue'])?.map((j) => j.id)).toEqual([1, 2, 3])
  })
})
