// Printer types
export type PrinterType = 'bambu' | 'prusa' | 'octoprint'
export type PrinterStatus =
  | 'IDLE'
  | 'READY'
  | 'PRINTING'
  | 'PREPARING'
  | 'FINISHED'
  | 'ERROR'
  | 'EJECTING'
  | 'COOLING'
  | 'PAUSED'
  | 'OFFLINE'

export interface Printer {
  name: string
  ip: string
  type: PrinterType
  status: PrinterStatus
  progress?: number
  current_file?: string
  order_id?: number | null
  cooldown_order_id?: number | null
  cooldown_target_temp?: number | null
  state?: PrinterStatus
  /** Resolved queue job id (order_id or cooldown_order_id) from API broadcast */
  queue_job_id?: number | null
  groups?: number[]
  group?: string
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
  // Error state information
  error_message?: string
  hms_alerts?: string[] // Bambu HMS (Health Management System) alerts
}

export interface PrinterFormData {
  name: string
  ip: string
  type: PrinterType
  api_key?: string
  serial_number?: string
  groups?: number[]
  group?: string
}

// Library catalog (reusable print templates)
export interface LibraryItem {
  id: number
  filename: string
  name?: string
  filepath?: string
  groups: (number | string)[]
  filament_g?: number
  ejection_enabled?: boolean
  ejection_code_id?: string
  ejection_code_name?: string
  cooldown_temp?: number | null
  created_at?: string
  updated_at?: string
}

// Print queue jobs
export type QueueJobStatus = 'pending' | 'partial' | 'fulfilled'

export interface QueueJobErrorEvent {
  at: string
  message: string
  printer?: string
  phase?: string
  batch_id?: string
  task_id?: string
}

export interface QueueJob {
  id: number
  library_item_id?: number | null
  filename: string
  name?: string
  quantity: number
  sent: number
  status: QueueJobStatus
  groups: (number | string)[]
  created_at?: string
  filepath?: string
  ejection_enabled?: boolean
  ejection_code_id?: string
  ejection_code_name?: string
  end_gcode?: string
  cooldown_temp?: number | null
  last_error?: string | null
  last_error_at?: string | null
  last_error_printer?: string | null
  last_error_phase?: string | null
  error_events?: QueueJobErrorEvent[]
}

/** @deprecated Use QueueJob — kept for gradual migration */
export type OrderStatus = QueueJobStatus

/** @deprecated Use QueueJob */
export interface Order extends QueueJob {
  priority?: number
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
  /** Total filament consumed (kilograms). */
  total_filament: number
  printers_count: number
  library_count: number
  /** Jobs waiting to start (sent === 0). */
  queue_pending_count: number
  /** Legacy: partial multi-copy jobs (0 < sent < quantity). */
  in_queue_count: number
  active_prints: number
  idle_printers: number
  completed_today: number
}

// Ejection status
export interface EjectionStatus {
  paused: boolean
  status: 'paused' | 'active'
}

// Ejection Code (stored G-code preset for auto-ejection)
export interface EjectionCode {
  id: string
  name: string
  gcode: string
  source_filename?: string
  created_at: string
  updated_at?: string
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
