import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ApiResponse, QueueJob } from '@/types'

export function useQueue() {
  return useQuery({
    queryKey: ['queue'],
    queryFn: () => api.get<QueueJob[]>('/queue'),
    staleTime: 5000,
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
    mutationFn: (id: number) => api.delete<ApiResponse>(`/queue/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
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
    mutationFn: ({ id, quantity }: { id: number; quantity: number }) =>
      api.patch<ApiResponse>(`/queue/${id}`, { quantity }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
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
      return api.patch<ApiResponse>(`/queue/${id}/ejection`, body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export function useBulkDeleteQueue() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ids: number[]) =>
      api.post<{ success: boolean; deleted_count: number }>('/queue/bulk-delete', { ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}
