import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useIsApiConnected } from '@/hooks/useApiConnection'
import { api } from '@/lib/api'
import { optimisticRemoveLibraryItems, restoreLibraryCache } from '@/lib/optimistic-library-cache'
import { libraryRefetchInterval } from '@/lib/refetch-intervals'
import type { ApiResponse, LibraryItem } from '@/types'

export interface BulkDeleteLibraryResult {
  success: boolean
  deleted_count: number
  failures: Array<{ id: number; error: string }>
}

export interface BulkUpdateLibraryPayload {
  ids: number[]
  groups?: (number | string)[]
  ejectionEnabled?: boolean
  ejectionCodeId?: string | null
  endGcode?: string
  cooldownTemp?: number | null
}

export interface BulkUpdateLibraryResult {
  success: boolean
  updated_count: number
  failures: Array<{ id: number; error: string }>
}

export function useLibrary() {
  const isConnected = useIsApiConnected()
  return useQuery({
    queryKey: ['library'],
    queryFn: () => api.get<LibraryItem[]>('/library'),
    staleTime: 5000,
    refetchInterval: (query) => libraryRefetchInterval(isConnected, query.state.dataUpdatedAt),
  })
}

export function useCreateLibraryItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (formData: FormData) => api.upload<ApiResponse>('/library', formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

export function useUpdateLibraryItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<LibraryItem> }) =>
      api.patch<ApiResponse>(`/library/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

export function useUpdateLibraryEjection() {
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
      return api.patch<ApiResponse>(`/library/${id}/ejection`, body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

export function useDeleteLibraryItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<ApiResponse>(`/library/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

export function useReplaceLibraryFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => {
      const formData = new FormData()
      formData.append('file', file)
      return api.upload<ApiResponse>(`/library/${id}/file`, formData, { method: 'PUT' })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export interface ImportLibraryResult {
  success: boolean
  success_count: number
  failed_count: number
  failures: Array<{ row: number; error: string }>
}

export function useBulkDeleteLibrary() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['bulkDeleteLibrary'],
    mutationFn: (ids: number[]) =>
      api.post<BulkDeleteLibraryResult>('/library/bulk-delete', { ids }),
    onMutate: async (ids) => {
      const { previous } = await optimisticRemoveLibraryItems(queryClient, ids)
      return { previous }
    },
    onSuccess: (data) => {
      const failures = data?.failures ?? []
      const deleted = data?.deleted_count ?? 0
      if (deleted > 0) {
        toast.success(
          failures.length > 0
            ? `${deleted} deleted; ${failures.length} could not be deleted`
            : `${deleted} library item(s) deleted`
        )
      } else if (failures.length > 0) {
        toast.error(failures[0]?.error ?? 'Could not delete selected items')
      }
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
    onError: (_err, _ids, context) => {
      restoreLibraryCache(queryClient, context?.previous)
      toast.error('Failed to delete library items')
    },
  })
}

export function useBulkUpdateLibrary() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: BulkUpdateLibraryPayload) => {
      const body: Record<string, unknown> = { ids: payload.ids }
      if (payload.groups !== undefined) body.groups = payload.groups
      if (payload.ejectionEnabled !== undefined) body.ejection_enabled = payload.ejectionEnabled
      if (payload.ejectionCodeId !== undefined) body.ejection_code_id = payload.ejectionCodeId
      if (payload.endGcode !== undefined) body.end_gcode = payload.endGcode
      if (payload.cooldownTemp !== undefined) body.cooldown_temp = payload.cooldownTemp
      return api.post<BulkUpdateLibraryResult>('/library/bulk-update', body)
    },
    onSuccess: (data) => {
      const failures = data?.failures ?? []
      const updated = data?.updated_count ?? 0
      if (updated > 0) {
        toast.success(
          failures.length > 0
            ? `${updated} updated; ${failures.length} could not be updated`
            : `${updated} library item(s) updated`
        )
      } else if (failures.length > 0) {
        toast.error(failures[0]?.error ?? 'Could not update selected items')
      }
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
    onError: () => {
      toast.error('Failed to update library items')
    },
  })
}

export function useImportLibrary() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File): Promise<ImportLibraryResult> => {
      const formData = new FormData()
      formData.append('file', file)
      return api.upload<ImportLibraryResult>('/library/import', formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })
}
