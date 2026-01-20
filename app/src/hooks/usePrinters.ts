import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Printer, PrinterFormData, ApiResponse } from '@/types'

export function usePrinters() {
  return useQuery({
    queryKey: ['printers'],
    queryFn: () => api.get<Printer[]>('/printers'),
    staleTime: 5000,
    refetchInterval: 10000, // Refetch every 10 seconds as backup to socket updates
  })
}

export function usePrinter(name: string) {
  return useQuery({
    queryKey: ['printers', name],
    queryFn: () => api.get<Printer>(`/printers/${name}`),
    enabled: !!name,
  })
}

export function useAddPrinter() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: PrinterFormData) =>
      api.post<ApiResponse>('/printers', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

export function useDeletePrinter() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.delete<ApiResponse>(`/printers/${name}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

export function useUpdatePrinter() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, data }: { name: string; data: Partial<PrinterFormData> }) =>
      api.patch<ApiResponse>(`/printers/${name}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

// Printer actions
export function useSendPrint() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ printerName, orderId }: { printerName: string; orderId: number }) =>
      api.post<ApiResponse>(`/printers/${printerName}/print`, { order_id: orderId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useStopPrint() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (printerName: string) =>
      api.post<ApiResponse>(`/printers/${printerName}/stop`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

export function usePausePrint() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (printerName: string) =>
      api.post<ApiResponse>(`/printers/${printerName}/pause`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

export function useResumePrint() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (printerName: string) =>
      api.post<ApiResponse>(`/printers/${printerName}/resume`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

export function useMarkReady() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (printerName: string) =>
      api.post<ApiResponse>(`/printers/${printerName}/ready`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}

export function useClearError() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (printerName: string) =>
      api.post<ApiResponse>(`/clear_error_by_name`, { printer_name: printerName }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] })
    },
  })
}
