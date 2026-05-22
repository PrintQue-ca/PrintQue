import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
  optimisticPatchQueueJobEjection,
  optimisticRemoveQueueJobs,
  type QueueEjectionPatch,
  restoreQueueCache,
} from '@/lib/optimistic-queue-cache'
import type { ApiResponse, QueueJob } from '@/types'

/** @deprecated Use useQueue */
export function useOrders() {
  return useQuery({
    queryKey: ['queue'],
    queryFn: () => api.get<QueueJob[]>('/queue'),
    staleTime: 5000,
  })
}

export function useOrder(id: number) {
  return useQuery({
    queryKey: ['orders', id],
    queryFn: () => api.get<QueueJob>(`/queue/${id}`),
    enabled: !!id,
  })
}

export function useCreateOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (formData: FormData) => api.upload<ApiResponse>('/library', formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

export function useDeleteOrder() {
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

export function useUpdateOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<QueueJob> }) =>
      api.patch<ApiResponse>(`/queue/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export function useMoveOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, direction }: { id: number; direction: 'up' | 'down' }) =>
      api.post<ApiResponse>(`/queue/${id}/move`, { direction }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export function useUpdateQuantity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, quantity }: { id: number; quantity: number }) =>
      api.patch<ApiResponse>(`/queue/${id}`, { quantity }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

export function useReorderOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['reorderQueueJob'],
    mutationFn: ({ id, newIndex }: { id: number; newIndex: number }) =>
      api.post<ApiResponse>(`/queue/${id}/reorder`, { new_index: newIndex }),
    onMutate: async ({ id, newIndex }) => {
      await queryClient.cancelQueries({ queryKey: ['queue'] })
      const previousOrders = queryClient.getQueryData<QueueJob[]>(['queue'])
      if (previousOrders) {
        const oldIndex = previousOrders.findIndex((order) => order.id === id)
        if (oldIndex !== -1) {
          const newOrders = [...previousOrders]
          const [movedOrder] = newOrders.splice(oldIndex, 1)
          newOrders.splice(newIndex, 0, movedOrder)
          queryClient.setQueryData(['queue'], newOrders)
        }
      }
      return { previousOrders }
    },
    onError: (_err, _variables, context) => {
      if (context?.previousOrders) {
        queryClient.setQueryData(['queue'], context.previousOrders)
      }
    },
    // No onSettled/onSuccess - trust the optimistic update, don't refetch
  })
}

export function useUpdateOrderEjection() {
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
      // `null` clears the cooldown, `undefined` leaves it unchanged
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

export function useBulkDeleteOrders() {
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

export interface ImportOrdersResult {
  success: boolean
  success_count: number
  failed_count: number
  failures: Array<{ row: number; error: string }>
}

export function useImportOrders() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File): Promise<ImportOrdersResult> => {
      const formData = new FormData()
      formData.append('file', file)
      return api.upload<ImportOrdersResult>('/library/import', formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}
