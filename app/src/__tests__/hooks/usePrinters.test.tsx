/**
 * Tests for usePrinters hooks.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { usePrinters, useAddPrinter, useDeletePrinter, useStopPrint } from '../../hooks/usePrinters'
import type { Printer } from '../../types'

// Mock the API module
vi.mock('../../lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
  },
}))

import { api } from '../../lib/api'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

const mockPrinters: Printer[] = [
  {
    name: 'Printer 1',
    ip: '192.168.1.100',
    type: 'prusa',
    status: 'READY',
  },
  {
    name: 'Printer 2',
    ip: '192.168.1.101',
    type: 'bambu',
    status: 'PRINTING',
    progress: 50,
  },
]

describe('usePrinters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('usePrinters hook', () => {
    it('should fetch printers successfully', async () => {
      vi.mocked(api.get).mockResolvedValue(mockPrinters)

      const { result } = renderHook(() => usePrinters(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockPrinters)
      expect(api.get).toHaveBeenCalledWith('/printers')
    })

    it('should handle fetch error', async () => {
      vi.mocked(api.get).mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => usePrinters(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toBeDefined()
    })
  })

  describe('useAddPrinter hook', () => {
    it('should add printer successfully', async () => {
      vi.mocked(api.post).mockResolvedValue({ success: true })

      const { result } = renderHook(() => useAddPrinter(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({
        name: 'New Printer',
        ip: '192.168.1.102',
        type: 'prusa',
        api_key: 'test_key',
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.post).toHaveBeenCalledWith('/printers', {
        name: 'New Printer',
        ip: '192.168.1.102',
        type: 'prusa',
        api_key: 'test_key',
      })
    })

    it('should handle add error', async () => {
      vi.mocked(api.post).mockRejectedValue(new Error('Printer limit reached'))

      const { result } = renderHook(() => useAddPrinter(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({
        name: 'New Printer',
        ip: '192.168.1.102',
        type: 'prusa',
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  describe('useDeletePrinter hook', () => {
    it('should delete printer successfully', async () => {
      vi.mocked(api.delete).mockResolvedValue({ success: true })

      const { result } = renderHook(() => useDeletePrinter(), {
        wrapper: createWrapper(),
      })

      result.current.mutate('Printer 1')

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.delete).toHaveBeenCalledWith('/printers/Printer 1')
    })
  })

  describe('useStopPrint hook', () => {
    it('should stop print successfully', async () => {
      vi.mocked(api.post).mockResolvedValue({ success: true })

      const { result } = renderHook(() => useStopPrint(), {
        wrapper: createWrapper(),
      })

      result.current.mutate('Printer 1')

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.post).toHaveBeenCalledWith('/printers/Printer 1/stop')
    })
  })
})
