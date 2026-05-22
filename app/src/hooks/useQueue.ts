import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAdaptiveRefetchInterval } from '@/hooks/useApiConnection'
import { api } from '@/lib/api'
import { createDebouncedQueueQuantityActions } from '@/lib/debounced-queue-quantity'
import {
  optimisticPatchQueueJobEjection,
  optimisticRemoveQueueJobs,
  type QueueEjectionPatch,
  restoreQueueCache,
} from '@/lib/optimistic-queue-cache'
import type { ApiResponse, QueueJob } from '@/types'

export function useQueue() {
  const refetchInterval = useAdaptiveRefetchInterval()
  return useQuery({
    queryKey: ['queue'],
    queryFn: () => api.get<QueueJob[]>('/queue'),
    staleTime: 5000,
    refetchInterval,
  })
}

export function useBulkEnqueue() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (
      items: Array<{ library_item_id: number; quantity: number; groups?: (number | string)[] }>
    ) =>
      api.post<{ success: boolean; created_ids: number[]; count: number }>('/queue/bulk', {
        items,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export function useDeleteQueueJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['deleteQueueJob'],
    mutationFn: (id: number) => api.delete<ApiResponse>(`/queue/${id}`),
    onMutate: async (id) => {
      const { previous } = await optimisticRemoveQueueJobs(queryClient, id)
      return { previous }
    },
    onError: (_err, _id, context) => {
      restoreQueueCache(queryClient, context?.previous)
      void import('sonner').then(({ toast }) => {
        toast.error('Failed to delete queue job')
      })
    },
  })
}

export function useUpdateQueueJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<QueueJob> }) =>
      api.patch<ApiResponse>(`/queue/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export function useUpdateQueueQuantity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['updateQueueQuantity'],
    mutationFn: ({ id, quantity }: { id: number; quantity: number }) =>
      api.patch<ApiResponse>(`/queue/${id}`, { quantity }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

/** Optimistic quantity edits with debounced PATCH (for queue table +/- controls). */
export function useDebouncedQueueQuantity() {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationKey: ['updateQueueQuantity'],
    mutationFn: ({ id, quantity }: { id: number; quantity: number }) =>
      api.patch<ApiResponse>(`/queue/${id}`, { quantity }),
    onError: () => {
      void import('sonner').then(({ toast }) => {
        toast.error('Failed to update quantity')
      })
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })

  return createDebouncedQueueQuantityActions(queryClient, mutation.mutate)
}

export function useReorderQueueJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['reorderQueueJob'],
    mutationFn: ({ id, newIndex }: { id: number; newIndex: number }) =>
      api.post<ApiResponse>(`/queue/${id}/reorder`, { new_index: newIndex }),
    onMutate: async ({ id, newIndex }) => {
      await queryClient.cancelQueries({ queryKey: ['queue'] })
      const previous = queryClient.getQueryData<QueueJob[]>(['queue'])
      if (previous) {
        const oldIndex = previous.findIndex((job) => job.id === id)
        if (oldIndex !== -1) {
          const next = [...previous]
          const [moved] = next.splice(oldIndex, 1)
          next.splice(newIndex, 0, moved)
          queryClient.setQueryData(['queue'], next)
        }
      }
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['queue'], context.previous)
      }
    },
  })
}

export function useUpdateQueueEjection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ejectionEnabled,
      ejectionCodeId,
      endGcode,
      cooldownTemp,
    }: {
      id: number
      ejectionEnabled?: boolean
      ejectionCodeId?: string | null
      endGcode?: string
      cooldownTemp?: number | null
    }) => {
      const body: Record<string, unknown> = {}
      if (ejectionEnabled !== undefined) body.ejection_enabled = ejectionEnabled
      if (ejectionCodeId !== undefined) body.ejection_code_id = ejectionCodeId
      if (endGcode !== undefined) body.end_gcode = endGcode
      if (cooldownTemp !== undefined) body.cooldown_temp = cooldownTemp
      return api.patch<ApiResponse & { job?: QueueJob }>(`/queue/${id}/ejection`, body)
    },
    onMutate: async (variables) => {
      const patch: QueueEjectionPatch = {}
      if (variables.ejectionEnabled !== undefined)
        patch.ejection_enabled = variables.ejectionEnabled
      if (variables.ejectionCodeId !== undefined) patch.ejection_code_id = variables.ejectionCodeId
      if (variables.cooldownTemp !== undefined) patch.cooldown_temp = variables.cooldownTemp
      if (Object.keys(patch).length === 0) return { previous: undefined }
      return optimisticPatchQueueJobEjection(queryClient, variables.id, patch)
    },
    onSuccess: (data) => {
      const job = data?.job
      if (job) {
        queryClient.setQueryData<QueueJob[]>(
          ['queue'],
          (old) => old?.map((j) => (j.id === job.id ? { ...j, ...job } : j)) ?? old
        )
      }
    },
    onError: (_err, _variables, context) => {
      restoreQueueCache(queryClient, context?.previous)
    },
  })
}

export function useBulkDeleteQueue() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['bulkDeleteQueueJob'],
    mutationFn: (ids: number[]) =>
      api.post<{ success: boolean; deleted_count: number }>('/queue/bulk-delete', { ids }),
    onMutate: async (ids) => {
      const { previous } = await optimisticRemoveQueueJobs(queryClient, ids)
      return { previous }
    },
    onError: (_err, _ids, context) => {
      restoreQueueCache(queryClient, context?.previous)
      void import('sonner').then(({ toast }) => {
        toast.error('Failed to delete queue jobs')
      })
    },
  })
}
