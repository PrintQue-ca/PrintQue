// Printer types
export type PrinterType = 'bambu' | 'prusa' | 'octoprint'
export type PrinterStatus = 'IDLE' | 'PRINTING' | 'FINISHED' | 'ERROR' | 'EJECTING' | 'PAUSED' | 'OFFLINE'

export interface Printer {
  name: string
  ip: string
  type: PrinterType
  status: PrinterStatus
  progress?: number
  current_file?: string
  groups?: number[]
  api_key?: string
  serial_number?: string
  model?: string
  time_remaining?: number
  filament_used?: number
  layer_current?: number
  layer_total?: number
  bed_temp?: number
  nozzle_temp?: number
  enabled?: boolean
}

export interface PrinterFormData {
  name: string
  ip: string
  type: PrinterType
  api_key?: string
  serial_number?: string
  groups?: number[]
}

// Order types
export type OrderStatus = 'active' | 'completed' | 'paused'

export interface Order {
  id: number
  filename: string
  quantity: number
  sent: number
  priority: number
  groups: number[]
  status: OrderStatus
  created_at?: string
  filepath?: string
}

export interface OrderFormData {
  file: File
  quantity: number
  groups: number[]
}

// Group types
export interface Group {
  id: number
  name: string
  color?: string
}

// Stats types
export interface Stats {
  total_filament: number
  printers_count: number
  library_count: number
  in_queue_count: number
  active_prints: number
  idle_printers: number
  completed_today: number
}

// License types
export type LicenseTier = 'free' | 'basic' | 'pro' | 'enterprise'

export interface License {
  valid: boolean
  tier: LicenseTier
  max_printers: number
  expires_at?: string
  machine_id?: string
}

// Ejection status
export interface EjectionStatus {
  paused: boolean
  status: 'paused' | 'active'
}

// API Response types
export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

// System info
export interface SystemInfo {
  version: string
  uptime: number
  memory_usage: number
  cpu_usage: number
  python_version: string
  platform: string
}
