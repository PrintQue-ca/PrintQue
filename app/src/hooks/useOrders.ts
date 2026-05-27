import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { optimisticRemoveQueueJobs, restoreQueueCache } from '@/lib/optimistic-queue-cache'
import type { ApiResponse, Order } from '@/types'

export function useOrders() {
  return useQuery({
    queryKey: ['queue'],
    queryFn: () => api.get<Order[]>('/queue'),
    staleTime: 5000,
  })
}

export function useOrder(id: number) {
  return useQuery({
    queryKey: ['queue', id],
    queryFn: () => api.get<Order>(`/queue/${id}`),
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
    mutationFn: (id: number) => api.delete<ApiResponse>(`/queue/${id}`),
    onMutate: async (id) => {
      const { previous } = await optimisticRemoveQueueJobs(queryClient, id)
      return { previous }
    },
    onError: (_err, _id, context) => {
      restoreQueueCache(queryClient, context?.previous)
    },
  })
}

export function useUpdateOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Order> }) =>
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
    },
  })
}

export function useReorderOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['reorderOrder'],
    mutationFn: ({ id, newIndex }: { id: number; newIndex: number }) =>
      api.post<ApiResponse>(`/queue/${id}/reorder`, { new_index: newIndex }),
    onMutate: async ({ id, newIndex }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['queue'] })

      // Snapshot the previous value
      const previousOrders = queryClient.getQueryData<Order[]>(['queue'])

      // Optimistically update the cache
      if (previousOrders) {
        const oldIndex = previousOrders.findIndex((order) => order.id === id)
        if (oldIndex !== -1) {
          const newOrders = [...previousOrders]
          const [movedOrder] = newOrders.splice(oldIndex, 1)
          newOrders.splice(newIndex, 0, movedOrder)
          queryClient.setQueryData(['queue'], newOrders)
        }
      }

      // Return context with the previous value
      return { previousOrders }
    },
    onError: (_err, _variables, context) => {
      // Rollback to the previous value on error
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
      ejectionCodeName,
      endGcode,
    }: {
      id: number
      ejectionEnabled: boolean
      ejectionCodeId?: string
      ejectionCodeName?: string
      endGcode?: string
    }) =>
      api.patch<ApiResponse>(`/queue/${id}/ejection`, {
        ejection_enabled: ejectionEnabled,
        ejection_code_id: ejectionCodeId,
        ejection_code_name: ejectionCodeName,
        end_gcode: endGcode,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

/** @deprecated Use useBulkDeleteQueue */
export { useBulkDeleteQueue as useBulkDeleteOrders } from './useQueue'
