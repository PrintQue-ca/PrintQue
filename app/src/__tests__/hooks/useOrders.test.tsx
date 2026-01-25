/**
 * Tests for useOrders hooks.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCreateOrder, useDeleteOrder, useOrders, useUpdateOrder } from '../../hooks/useOrders'
import type { Order } from '../../types'

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
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

const mockOrders: Order[] = [
  {
    id: 1,
    filename: 'test_part.gcode',
    name: 'Test Order',
    quantity: 5,
    sent: 2,
    priority: 1,
    groups: [0],
    status: 'active',
  },
  {
    id: 2,
    filename: 'another_part.3mf',
    quantity: 1,
    sent: 0,
    priority: 2,
    groups: [0],
    status: 'active',
  },
]

describe('useOrders', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useOrders hook', () => {
    it('should fetch orders successfully', async () => {
      vi.mocked(api.get).mockResolvedValue(mockOrders)

      const { result } = renderHook(() => useOrders(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockOrders)
      expect(api.get).toHaveBeenCalledWith('/orders')
    })

    it('should handle fetch error', async () => {
      vi.mocked(api.get).mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useOrders(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  describe('useCreateOrder hook', () => {
    it('should create order successfully', async () => {
      vi.mocked(api.upload).mockResolvedValue({ success: true, order_id: 3 })

      const { result } = renderHook(() => useCreateOrder(), {
        wrapper: createWrapper(),
      })

      const formData = new FormData()
      formData.append('file', new Blob(['test']), 'test.gcode')
      formData.append('quantity', '1')

      result.current.mutate(formData)

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.upload).toHaveBeenCalledWith('/orders', formData)
    })

    it('should handle create error', async () => {
      vi.mocked(api.upload).mockRejectedValue(new Error('Invalid file'))

      const { result } = renderHook(() => useCreateOrder(), {
        wrapper: createWrapper(),
      })

      const formData = new FormData()
      result.current.mutate(formData)

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  describe('useDeleteOrder hook', () => {
    it('should delete order successfully', async () => {
      vi.mocked(api.delete).mockResolvedValue({ success: true })

      const { result } = renderHook(() => useDeleteOrder(), {
        wrapper: createWrapper(),
      })

      result.current.mutate(1)

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.delete).toHaveBeenCalledWith('/orders/1')
    })
  })

  describe('useUpdateOrder hook', () => {
    it('should update order successfully', async () => {
      vi.mocked(api.patch).mockResolvedValue({ success: true })

      const { result } = renderHook(() => useUpdateOrder(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({ id: 1, data: { quantity: 10 } })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.patch).toHaveBeenCalledWith('/orders/1', { quantity: 10 })
    })
  })
})
