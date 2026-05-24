import type { BedSize, Point3 } from './gcode-simulator'

export interface BedPreset {
  id: string
  label: string
  size: BedSize
  /** Typical post-print toolhead position for path preview */
  simulationStart?: Point3
  /** Machine-coordinate bounds for preview (Bambu uses offsets, not 0..bedSize) */
  simulationBounds?: { min: Point3; max: Point3 }
}

export const BED_PRESETS: BedPreset[] = [
  { id: 'bambu-256', label: 'Bambu X1C / P1S (256mm)', size: { x: 256, y: 256, z: 256 } },
  { id: 'bambu-a1', label: 'Bambu A1 (256×256)', size: { x: 256, y: 256, z: 256 } },
  {
    id: 'bambu-a1-mini',
    label: 'Bambu A1 Mini (180×180)',
    size: { x: 180, y: 180, z: 180 },
    simulationStart: { x: 180, y: 180, z: 30 },
    simulationBounds: {
      min: { x: 50, y: -4, z: 0 },
      max: { x: 310, y: 310, z: 180 },
    },
  },
  { id: 'prusa-mk4', label: 'Prusa MK4 / MK3S+ (250×210)', size: { x: 250, y: 210, z: 210 } },
  { id: 'prusa-mini', label: 'Prusa Mini (180×180)', size: { x: 180, y: 180, z: 180 } },
  { id: 'ender-3', label: 'Ender 3 (220×220)', size: { x: 220, y: 220, z: 250 } },
]

export const DEFAULT_PRESET_ID = 'bambu-256'

export interface ViewFrame {
  minX: number
  maxX: number
  minY: number
  maxY: number
  minZ: number
  maxZ: number
}

export function getViewFrame(preset: BedPreset): ViewFrame {
  if (preset.simulationBounds) {
    const { min, max } = preset.simulationBounds
    return {
      minX: min.x,
      maxX: max.x,
      minY: min.y,
      maxY: max.y,
      minZ: min.z,
      maxZ: max.z,
    }
  }
  return {
    minX: 0,
    maxX: preset.size.x,
    minY: 0,
    maxY: preset.size.y,
    minZ: 0,
    maxZ: preset.size.z,
  }
}

export function getPresetById(id: string): BedPreset | undefined {
  return BED_PRESETS.find((p) => p.id === id)
}

export function guessPresetFromModel(model?: string): BedPreset {
  const fallback = BED_PRESETS[0]
  if (!model) return fallback

  const m = model.toLowerCase()
  if (m.includes('a1') && m.includes('mini')) return getPresetById('bambu-a1-mini') ?? fallback
  if (m.includes('a1')) return getPresetById('bambu-a1') ?? fallback
  if (m.includes('x1') || m.includes('p1')) return getPresetById('bambu-256') ?? fallback
  if (m.includes('mk4') || m.includes('mk3')) return getPresetById('prusa-mk4') ?? fallback
  if (m.includes('mini')) return getPresetById('prusa-mini') ?? fallback
  if (m.includes('ender')) return getPresetById('ender-3') ?? fallback

  return fallback
}
