import type { MoveSegment } from './gcode-simulator'

export interface SpeedRange {
  min: number
  max: number
}

const SPEED_COLOR_SLOW = { r: 34, g: 197, b: 94 }
const SPEED_COLOR_FAST = { r: 239, g: 68, b: 68 }

export function getSegmentFeedrate(seg: MoveSegment): number {
  return seg.feedrate ?? (seg.rapid ? 6000 : 1500)
}

export function getSpeedRange(segments: MoveSegment[]): SpeedRange {
  if (segments.length === 0) return { min: 0, max: 1 }
  const speeds = segments.map(getSegmentFeedrate)
  return { min: Math.min(...speeds), max: Math.max(...speeds) }
}

/** Green (slow) → red (fast) by feedrate mm/min */
export function speedToColor(speed: number, range: SpeedRange): string {
  if (range.max <= range.min) {
    return `rgb(${SPEED_COLOR_SLOW.r},${SPEED_COLOR_SLOW.g},${SPEED_COLOR_SLOW.b})`
  }
  const t = Math.max(0, Math.min(1, (speed - range.min) / (range.max - range.min)))
  const r = Math.round(SPEED_COLOR_SLOW.r + (SPEED_COLOR_FAST.r - SPEED_COLOR_SLOW.r) * t)
  const g = Math.round(SPEED_COLOR_SLOW.g + (SPEED_COLOR_FAST.g - SPEED_COLOR_SLOW.g) * t)
  const b = Math.round(SPEED_COLOR_SLOW.b + (SPEED_COLOR_FAST.b - SPEED_COLOR_SLOW.b) * t)
  return `rgb(${r},${g},${b})`
}

export const SPEED_GRADIENT = {
  slow: SPEED_COLOR_SLOW,
  fast: SPEED_COLOR_FAST,
} as const
