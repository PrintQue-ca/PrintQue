export interface Point3 {
  x: number
  y: number
  z: number
}

export interface BedSize {
  x: number
  y: number
  z: number
}

export interface MoveSegment {
  from: Point3
  to: Point3
  command: string
  lineNumber: number
  rapid: boolean
  feedrate: number | null
}

export type MarkerKind = 'home' | 'dwell' | 'wait_temp' | 'sync' | 'stop' | 'set_position'

export interface Marker {
  position: Point3
  kind: MarkerKind
  lineNumber: number
  label: string
}

export type StepKind = 'move' | 'dwell' | 'home' | 'set_position' | 'wait_temp' | 'sync' | 'stop'

export interface SimulationStep {
  lineNumber: number
  kind: StepKind
  from: Point3
  to: Point3
  label: string
  durationMs: number | null
  segmentIndex: number | null
  markerIndex: number | null
}

export interface SimulationResult {
  segments: MoveSegment[]
  markers: Marker[]
  steps: SimulationStep[]
  warnings: string[]
  bounds: { min: Point3; max: Point3 }
}

interface MachineState {
  x: number
  y: number
  z: number
  f: number
  absolute: boolean
}

const DEFAULT_RAPID_SPEED = 6000
const DEFAULT_FEED_SPEED = 1500

function parseParams(tokens: string[]): Map<string, number> {
  const params = new Map<string, number>()
  for (const token of tokens) {
    if (token.length < 2) continue
    const letter = token[0].toUpperCase()
    const value = Number.parseFloat(token.substring(1))
    if (!Number.isNaN(value)) {
      params.set(letter, value)
    }
  }
  return params
}

function distance3d(a: Point3, b: Point3): number {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const dz = b.z - a.z
  return Math.sqrt(dx * dx + dy * dy + dz * dz)
}

function computeMoveDuration(from: Point3, to: Point3, feedrate: number): number {
  const dist = distance3d(from, to)
  if (dist === 0 || feedrate <= 0) return 0
  return (dist / (feedrate / 60)) * 1000
}

function sampleArc(
  from: Point3,
  to: Point3,
  params: Map<string, number>,
  clockwise: boolean,
  subdivisions = 24
): Point3[] {
  const cx = from.x + (params.get('I') ?? 0)
  const cy = from.y + (params.get('J') ?? 0)

  const startAngle = Math.atan2(from.y - cy, from.x - cx)
  let endAngle = Math.atan2(to.y - cy, to.x - cx)

  if (clockwise) {
    while (endAngle >= startAngle) endAngle -= 2 * Math.PI
  } else {
    while (endAngle <= startAngle) endAngle += 2 * Math.PI
  }

  const totalAngle = endAngle - startAngle
  const points: Point3[] = []
  const r = Math.sqrt((from.x - cx) ** 2 + (from.y - cy) ** 2)

  for (let i = 1; i <= subdivisions; i++) {
    const t = i / subdivisions
    const angle = startAngle + totalAngle * t
    points.push({
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
      z: from.z + (to.z - from.z) * t,
    })
  }

  return points
}

export function simulateGcode(
  gcode: string,
  options: { homePosition?: Point3; appendM400?: boolean } = {}
): SimulationResult {
  const homePos = options.homePosition ?? { x: 0, y: 0, z: 0 }

  let rawLines = gcode.split('\n')

  if (options.appendM400) {
    const hasM400 = rawLines.some((l) => l.split(';')[0].trim().toUpperCase().includes('M400'))
    if (!hasM400) {
      rawLines = [...rawLines, 'M400']
    }
  }

  const state: MachineState = {
    x: homePos.x,
    y: homePos.y,
    z: homePos.z,
    f: DEFAULT_RAPID_SPEED,
    absolute: true,
  }

  const segments: MoveSegment[] = []
  const markers: Marker[] = []
  const steps: SimulationStep[] = []
  const warnings: string[] = []

  const pos = (): Point3 => ({ x: state.x, y: state.y, z: state.z })

  for (let i = 0; i < rawLines.length; i++) {
    const lineNumber = i + 1
    const codePart = rawLines[i].split(';')[0].trim()
    if (!codePart) continue

    const tokens = codePart.split(/\s+/)
    const cmd = tokens[0].toUpperCase()
    const params = parseParams(tokens.slice(1))

    switch (cmd) {
      case 'G0':
      case 'G1': {
        const rapid = cmd === 'G0'
        const from = pos()
        const feedParam = params.get('F')
        if (feedParam != null) state.f = feedParam

        if (state.absolute) {
          if (params.has('X')) state.x = params.get('X')!
          if (params.has('Y')) state.y = params.get('Y')!
          if (params.has('Z')) state.z = params.get('Z')!
        } else {
          if (params.has('X')) state.x += params.get('X')!
          if (params.has('Y')) state.y += params.get('Y')!
          if (params.has('Z')) state.z += params.get('Z')!
        }

        const to = pos()
        if (from.x !== to.x || from.y !== to.y || from.z !== to.z) {
          const feedrate = rapid ? DEFAULT_RAPID_SPEED : state.f || DEFAULT_FEED_SPEED
          const seg: MoveSegment = { from, to, command: cmd, lineNumber, rapid, feedrate }
          segments.push(seg)
          steps.push({
            lineNumber,
            kind: 'move',
            from,
            to,
            label: `${cmd} → (${to.x.toFixed(1)}, ${to.y.toFixed(1)}, ${to.z.toFixed(1)})`,
            durationMs: computeMoveDuration(from, to, feedrate),
            segmentIndex: segments.length - 1,
            markerIndex: null,
          })
        }
        break
      }

      case 'G2':
      case 'G3': {
        const clockwise = cmd === 'G2'
        const from = pos()
        const feedParam = params.get('F')
        if (feedParam != null) state.f = feedParam

        if (state.absolute) {
          if (params.has('X')) state.x = params.get('X')!
          if (params.has('Y')) state.y = params.get('Y')!
          if (params.has('Z')) state.z = params.get('Z')!
        } else {
          if (params.has('X')) state.x += params.get('X')!
          if (params.has('Y')) state.y += params.get('Y')!
          if (params.has('Z')) state.z += params.get('Z')!
        }

        const to = pos()
        const arcPoints = sampleArc(from, to, params, clockwise)

        let prevPt = from
        for (const pt of arcPoints) {
          segments.push({
            from: prevPt,
            to: pt,
            command: cmd,
            lineNumber,
            rapid: false,
            feedrate: state.f || DEFAULT_FEED_SPEED,
          })
          prevPt = pt
        }

        steps.push({
          lineNumber,
          kind: 'move',
          from,
          to,
          label: `${cmd} arc → (${to.x.toFixed(1)}, ${to.y.toFixed(1)})`,
          durationMs: null,
          segmentIndex: segments.length - 1,
          markerIndex: null,
        })
        break
      }

      case 'G28': {
        const from = pos()
        const noAxisSpecified = !params.has('X') && !params.has('Y') && !params.has('Z')
        const homeX = params.has('X') || noAxisSpecified
        const homeY = params.has('Y') || noAxisSpecified
        const homeZ = params.has('Z') || noAxisSpecified

        if (homeX) state.x = homePos.x
        if (homeY) state.y = homePos.y
        if (homeZ) state.z = homePos.z

        const axesLabel = [homeX && 'X', homeY && 'Y', homeZ && 'Z'].filter(Boolean).join('')
        const marker: Marker = {
          position: pos(),
          kind: 'home',
          lineNumber,
          label: `Home ${axesLabel}`,
        }
        markers.push(marker)
        steps.push({
          lineNumber,
          kind: 'home',
          from,
          to: pos(),
          label: marker.label,
          durationMs: null,
          segmentIndex: null,
          markerIndex: markers.length - 1,
        })
        break
      }

      case 'G90':
        state.absolute = true
        break

      case 'G91':
        state.absolute = false
        break

      case 'G20':
      case 'G21':
        // Units (inches / mm) — preview always uses mm; no motion.
        break

      case 'G92': {
        if (params.has('X')) state.x = params.get('X')!
        if (params.has('Y')) state.y = params.get('Y')!
        if (params.has('Z')) state.z = params.get('Z')!

        const marker: Marker = {
          position: pos(),
          kind: 'set_position',
          lineNumber,
          label: `Set origin (${state.x}, ${state.y}, ${state.z})`,
        }
        markers.push(marker)
        steps.push({
          lineNumber,
          kind: 'set_position',
          from: pos(),
          to: pos(),
          label: marker.label,
          durationMs: null,
          segmentIndex: null,
          markerIndex: markers.length - 1,
        })
        break
      }

      case 'G4': {
        let durationMs: number | null = null
        if (params.has('P')) durationMs = params.get('P')!
        else if (params.has('S')) durationMs = params.get('S')! * 1000

        const marker: Marker = {
          position: pos(),
          kind: 'dwell',
          lineNumber,
          label: durationMs != null ? `Dwell ${(durationMs / 1000).toFixed(1)}s` : 'Dwell',
        }
        markers.push(marker)
        steps.push({
          lineNumber,
          kind: 'dwell',
          from: pos(),
          to: pos(),
          label: marker.label,
          durationMs,
          segmentIndex: null,
          markerIndex: markers.length - 1,
        })
        break
      }

      case 'M400': {
        const marker: Marker = {
          position: pos(),
          kind: 'sync',
          lineNumber,
          label: 'Wait for moves (M400)',
        }
        markers.push(marker)
        steps.push({
          lineNumber,
          kind: 'sync',
          from: pos(),
          to: pos(),
          label: marker.label,
          durationMs: null,
          segmentIndex: null,
          markerIndex: markers.length - 1,
        })
        break
      }

      case 'M109':
      case 'M190': {
        const tempVal = params.get('S') ?? params.get('R')
        const target = cmd === 'M109' ? 'nozzle' : 'bed'
        const label = tempVal != null ? `Wait ${target} ${tempVal}°C` : `Wait ${target} temp`
        const marker: Marker = { position: pos(), kind: 'wait_temp', lineNumber, label }
        markers.push(marker)
        steps.push({
          lineNumber,
          kind: 'wait_temp',
          from: pos(),
          to: pos(),
          label,
          durationMs: 1000,
          segmentIndex: null,
          markerIndex: markers.length - 1,
        })
        break
      }

      case 'M0':
      case 'M1': {
        const marker: Marker = {
          position: pos(),
          kind: 'stop',
          lineNumber,
          label: cmd === 'M0' ? 'Stop' : 'Optional stop',
        }
        markers.push(marker)
        steps.push({
          lineNumber,
          kind: 'stop',
          from: pos(),
          to: pos(),
          label: marker.label,
          durationMs: null,
          segmentIndex: null,
          markerIndex: markers.length - 1,
        })
        break
      }

      default: {
        if (!cmd.startsWith('M') && !cmd.startsWith('T') && cmd.startsWith('G')) {
          warnings.push(`Line ${lineNumber}: unsupported command ${cmd}`)
        }
        break
      }
    }
  }

  const allPoints = [...segments.flatMap((s) => [s.from, s.to]), ...markers.map((m) => m.position)]

  const bounds = {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 0, y: 0, z: 0 },
  }

  if (allPoints.length > 0) {
    bounds.min = {
      x: Math.min(...allPoints.map((p) => p.x)),
      y: Math.min(...allPoints.map((p) => p.y)),
      z: Math.min(...allPoints.map((p) => p.z)),
    }
    bounds.max = {
      x: Math.max(...allPoints.map((p) => p.x)),
      y: Math.max(...allPoints.map((p) => p.y)),
      z: Math.max(...allPoints.map((p) => p.z)),
    }
  }

  return { segments, markers, steps, warnings, bounds }
}
