import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Stats, EjectionStatus, License, SystemInfo, Group, ApiResponse, EjectionCode } from '@/types'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => api.get<Stats>('/system/stats'),
    staleTime: 5000,
    refetchInterval: 30000,
  })
}

export function useFilamentUsage() {
  return useQuery({
    queryKey: ['stats', 'filament'],
    queryFn: () => api.get<{ total: number }>('/system/filament'),
    staleTime: 5000,
  })
}

export function useEjectionStatus() {
  return useQuery({
    queryKey: ['ejection'],
    queryFn: () => api.get<EjectionStatus>('/ejection/status'),
    staleTime: 2000,
  })
}

export function usePauseEjection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ApiResponse>('/ejection/pause'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ejection'] })
    },
  })
}

export function useResumeEjection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ApiResponse>('/ejection/resume'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ejection'] })
    },
  })
}

export function useLicense() {
  return useQuery({
    queryKey: ['license'],
    queryFn: () => api.get<License>('/system/license'),
    staleTime: 60000, // License doesn't change often
  })
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ['system', 'info'],
    queryFn: () => api.get<SystemInfo>('/system/info'),
    staleTime: 10000,
  })
}

export function useGroups() {
  return useQuery({
    queryKey: ['groups'],
    queryFn: () => api.get<Group[]>('/system/groups'),
    staleTime: 30000,
  })
}

export function useCreateGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      api.post<ApiResponse>('/system/groups', { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'] })
    },
  })
}

export function useDeleteGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<ApiResponse>(`/system/groups/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'] })
    },
  })
}

// Default ejection settings
export interface DefaultEjectionSettings {
  ejection_enabled: boolean
  end_gcode: string
}

export function useDefaultEjectionSettings() {
  return useQuery({
    queryKey: ['settings', 'default-ejection'],
    queryFn: () => api.get<DefaultEjectionSettings>('/settings/default-ejection'),
    staleTime: 30000,
  })
}

export function useSaveDefaultEjectionSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<DefaultEjectionSettings>) =>
      api.post<ApiResponse>('/settings/default-ejection', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'default-ejection'] })
    },
  })
}

// Ejection Codes (stored G-code presets)
interface EjectionCodesResponse {
  success: boolean
  ejection_codes: EjectionCode[]
}

interface CreateEjectionCodeResponse {
  success: boolean
  ejection_code: EjectionCode
  message: string
}

export function useEjectionCodes() {
  return useQuery({
    queryKey: ['ejection-codes'],
    queryFn: async () => {
      const response = await api.get<EjectionCodesResponse>('/ejection-codes')
      return response.ejection_codes
    },
    staleTime: 30000,
  })
}

export function useEjectionCode(id: string) {
  return useQuery({
    queryKey: ['ejection-codes', id],
    queryFn: async () => {
      const response = await api.get<{ success: boolean; ejection_code: EjectionCode }>(`/ejection-codes/${id}`)
      return response.ejection_code
    },
    enabled: !!id,
  })
}

export function useCreateEjectionCode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; gcode: string }) =>
      api.post<CreateEjectionCodeResponse>('/ejection-codes', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ejection-codes'] })
    },
  })
}

export function useUploadEjectionCode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (formData: FormData) =>
      api.upload<CreateEjectionCodeResponse>('/ejection-codes/upload', formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ejection-codes'] })
    },
  })
}

export function useUpdateEjectionCode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<{ name: string; gcode: string }> }) =>
      api.patch<CreateEjectionCodeResponse>(`/ejection-codes/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ejection-codes'] })
    },
  })
}

export function useDeleteEjectionCode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<ApiResponse>(`/ejection-codes/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ejection-codes'] })
    },
  })
}

export function useTestEjectionCode() {
  return useMutation({
    mutationFn: ({ codeId, printerName }: { codeId: string; printerName: string }) =>
      api.post<ApiResponse>(`/ejection-codes/${codeId}/test`, { printer_name: printerName }),
  })
}

// Logging configuration
export interface LoggingConfig {
  console_level: string
  file_level: string
  debug_flags: Record<string, boolean>
  available_levels: string[]
  available_flags: string[]
}

export function useLoggingConfig() {
  return useQuery({
    queryKey: ['logging'],
    queryFn: () => api.get<LoggingConfig>('/system/logging'),
    staleTime: 10000,
  })
}

export function useSetLogLevel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (level: string) =>
      api.post<ApiResponse & { level: string }>('/system/logging/level', { level }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['logging'] })
    },
  })
}

export function useSetDebugFlag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ flag, enabled }: { flag: string; enabled: boolean }) =>
      api.post<ApiResponse & { flags: Record<string, boolean> }>('/system/logging/debug-flags', { flag, enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['logging'] })
    },
  })
}
