import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ApiResponse, Order } from '@/types'

export function useOrders() {
  return useQuery({
    queryKey: ['orders'],
    queryFn: () => api.get<Order[]>('/orders'),
    staleTime: 5000,
  })
}

export function useOrder(id: number) {
  return useQuery({
    queryKey: ['orders', id],
    queryFn: () => api.get<Order>(`/orders/${id}`),
    enabled: !!id,
  })
}

export function useCreateOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (formData: FormData) => api.upload<ApiResponse>('/orders', formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useDeleteOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<ApiResponse>(`/orders/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useUpdateOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Order> }) =>
      api.patch<ApiResponse>(`/orders/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useMoveOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, direction }: { id: number; direction: 'up' | 'down' }) =>
      api.post<ApiResponse>(`/orders/${id}/move`, { direction }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useUpdateQuantity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, quantity }: { id: number; quantity: number }) =>
      api.patch<ApiResponse>(`/orders/${id}`, { quantity }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useReorderOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['reorderOrder'],
    mutationFn: ({ id, newIndex }: { id: number; newIndex: number }) =>
      api.post<ApiResponse>(`/orders/${id}/reorder`, { new_index: newIndex }),
    onMutate: async ({ id, newIndex }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['orders'] })

      // Snapshot the previous value
      const previousOrders = queryClient.getQueryData<Order[]>(['orders'])

      // Optimistically update the cache
      if (previousOrders) {
        const oldIndex = previousOrders.findIndex((order) => order.id === id)
        if (oldIndex !== -1) {
          const newOrders = [...previousOrders]
          const [movedOrder] = newOrders.splice(oldIndex, 1)
          newOrders.splice(newIndex, 0, movedOrder)
          queryClient.setQueryData(['orders'], newOrders)
        }
      }

      // Return context with the previous value
      return { previousOrders }
    },
    onError: (_err, _variables, context) => {
      // Rollback to the previous value on error
      if (context?.previousOrders) {
        queryClient.setQueryData(['orders'], context.previousOrders)
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
      api.patch<ApiResponse>(`/orders/${id}/ejection`, {
        ejection_enabled: ejectionEnabled,
        ejection_code_id: ejectionCodeId,
        ejection_code_name: ejectionCodeName,
        end_gcode: endGcode,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}
