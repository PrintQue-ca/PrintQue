import type { QueryClient } from '@tanstack/react-query'
import type { QueueJob } from '@/types'

export type QueueEjectionPatch = {
  ejection_enabled?: boolean
  ejection_code_id?: string | null
  cooldown_temp?: number | null
}

/** Patch ejection fields on a queue job in cache immediately; returns snapshot for rollback. */
export async function optimisticPatchQueueJobEjection(
  queryClient: QueryClient,
  id: number,
  patch: Partial<QueueEjectionPatch>
): Promise<{ previous: QueueJob[] | undefined }> {
  await queryClient.cancelQueries({ queryKey: ['queue'] })
  const previous = queryClient.getQueryData<QueueJob[]>(['queue'])
  if (previous) {
    queryClient.setQueryData(
      ['queue'],
      previous.map((job) => (job.id === id ? { ...job, ...patch } : job))
    )
  }
  return { previous }
}

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
