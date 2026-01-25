/**
 * Tests for the API client module.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api } from '../../lib/api'

describe('API Client', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('api.get', () => {
    it('should make GET request and return JSON data', async () => {
      const mockData = { printers: [], orders: [] }
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockData),
      })

      const result = await api.get('/system/stats')
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/system/stats')
      )
      expect(result).toEqual(mockData)
    })

    it('should throw error on non-ok response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        text: () => Promise.resolve('Not Found'),
      })

      await expect(api.get('/invalid')).rejects.toThrow('Not Found')
    })
  })

  describe('api.post', () => {
    it('should make POST request with JSON body', async () => {
      const mockResponse = { success: true }
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      })

      const result = await api.post('/printers', { name: 'Test' })
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/printers'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'Test' }),
        })
      )
      expect(result).toEqual(mockResponse)
    })

    it('should handle POST without body', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      })

      await api.post('/ejection/pause')
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/ejection/pause'),
        expect.objectContaining({
          method: 'POST',
          body: undefined,
        })
      )
    })
  })

  describe('api.patch', () => {
    it('should make PATCH request with JSON body', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      })

      await api.patch('/orders/1', { quantity: 5 })
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/orders/1'),
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ quantity: 5 }),
        })
      )
    })
  })

  describe('api.delete', () => {
    it('should make DELETE request', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      })

      await api.delete('/printers/test')
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/printers/test'),
        expect.objectContaining({
          method: 'DELETE',
        })
      )
    })
  })

  describe('api.upload', () => {
    it('should make POST request with FormData', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, order_id: 1 }),
      })

      const formData = new FormData()
      formData.append('file', new Blob(['test']), 'test.gcode')
      formData.append('quantity', '1')

      await api.upload('/orders', formData)
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/orders'),
        expect.objectContaining({
          method: 'POST',
          body: formData,
        })
      )
    })
  })
})
