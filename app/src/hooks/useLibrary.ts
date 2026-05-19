import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ApiResponse, LibraryItem } from '@/types'

export function useLibrary() {
  return useQuery({
    queryKey: ['library'],
    queryFn: () => api.get<LibraryItem[]>('/library'),
    staleTime: 5000,
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
