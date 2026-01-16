import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Stats, EjectionStatus, License, SystemInfo, Group, ApiResponse } from '@/types'

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
