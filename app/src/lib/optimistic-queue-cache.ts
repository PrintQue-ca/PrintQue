import type { QueryClient } from '@tanstack/react-query'
import type { QueueJob } from '@/types'

/** Remove job(s) from the queue cache immediately; returns snapshot for rollback. */
export async function optimisticRemoveQueueJobs(
  queryClient: QueryClient,
  ids: number | number[]
): Promise<{ previous: QueueJob[] | undefined }> {
  await queryClient.cancelQueries({ queryKey: ['queue'] })
  const previous = queryClient.getQueryData<QueueJob[]>(['queue'])
  const idSet = new Set(Array.isArray(ids) ? ids : [ids])
  if (previous) {
    queryClient.setQueryData(
      ['queue'],
      previous.filter((job) => !idSet.has(job.id))
    )
  }
  return { previous }
}

export function restoreQueueCache(
  queryClient: QueryClient,
  previous: QueueJob[] | undefined
): void {
  if (previous) {
    queryClient.setQueryData(['queue'], previous)
  }
}
