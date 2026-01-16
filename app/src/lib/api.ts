const API_BASE = import.meta.env.DEV ? 'http://localhost:5000/api/v1' : '/api/v1'

export const api = {
  get: async <T>(endpoint: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${endpoint}`)
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  post: async <T>(endpoint: string, data?: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  patch: async <T>(endpoint: string, data?: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  delete: async <T>(endpoint: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  // For file uploads
  upload: async <T>(endpoint: string, formData: FormData): Promise<T> => {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
}
