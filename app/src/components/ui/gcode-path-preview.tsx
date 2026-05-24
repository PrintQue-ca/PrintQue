import { AlertTriangle, ChevronLeft, ChevronRight, Pause, Play, RotateCcw } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useGcodePlayback } from '@/hooks/useGcodePlayback'
import {
  BED_PRESETS,
  DEFAULT_PRESET_ID,
  getPresetById,
  getViewFrame,
  type ViewFrame,
} from '@/lib/bed-presets'
import type { BedSize, Point3, SimulationResult } from '@/lib/gcode-simulator'
import { simulateGcode } from '@/lib/gcode-simulator'
import {
  getSegmentFeedrate,
  getSpeedRange,
  SPEED_GRADIENT,
  type SpeedRange,
  speedToColor,
} from '@/lib/gcode-speed'
import { cn } from '@/lib/utils'

interface GcodePathPreviewProps {
  gcode: string
  appendM400?: boolean
  className?: string
  onLineHover?: (lineNumber: number | null) => void
}

const SVG_PADDING = 20
const MARKER_RADIUS = 4

const MARKER_COLORS: Record<string, string> = {
  home: '#f59e0b',
  dwell: '#8b5cf6',
  wait_temp: '#ef4444',
  sync: '#3b82f6',
  stop: '#dc2626',
  set_position: '#6b7280',
}

const SPEED_OPTIONS = [0.5, 1, 2, 4]

function createProjectors(
  viewFrame: ViewFrame,
  svgW: number,
  svgH: number,
  projection: 'xy' | 'xz'
) {
  const spanX = viewFrame.maxX - viewFrame.minX
  const spanAxis2 =
    projection === 'xy' ? viewFrame.maxY - viewFrame.minY : viewFrame.maxZ - viewFrame.minZ
  const scaleX = (svgW - SVG_PADDING * 2) / spanX
  const scaleAxis2 = (svgH - SVG_PADDING * 2) / spanAxis2

  const tx = (p: Point3) => SVG_PADDING + (p.x - viewFrame.minX) * scaleX
  const ty = (p: Point3) => {
    const val = projection === 'xy' ? p.y : p.z
    const maxVal = projection === 'xy' ? viewFrame.maxY : viewFrame.maxZ
    return SVG_PADDING + (maxVal - val) * scaleAxis2
  }

  const segmentPath = (from: Point3, to: Point3) =>
    `M${tx(from).toFixed(1)},${ty(from).toFixed(1)} L${tx(to).toFixed(1)},${ty(to).toFixed(1)}`

  return { segmentPath }
}

interface ColoredSegmentLine {
  d: string
  color: string
  segmentIndex: number
  feedrate: number
  dashed: boolean
}

function buildColoredSegmentLines(
  segments: SimulationResult['segments'],
  viewFrame: ViewFrame,
  svgW: number,
  svgH: number,
  projection: 'xy' | 'xz',
  speedRange: SpeedRange,
  options?: { upToIndex?: number; progressOnLast?: number }
): ColoredSegmentLine[] {
  const { segmentPath } = createProjectors(viewFrame, svgW, svgH, projection)
  const limit =
    options?.upToIndex != null
      ? Math.min(options.upToIndex, segments.length - 1)
      : segments.length - 1

  const lines: ColoredSegmentLine[] = []

  for (let i = 0; i <= limit; i++) {
    const seg = segments[i]
    const from = seg.from
    let to = seg.to

    if (i === options?.upToIndex && (options.progressOnLast ?? 1) < 1) {
      const t = options.progressOnLast ?? 0
      to = {
        x: from.x + (to.x - from.x) * t,
        y: from.y + (to.y - from.y) * t,
        z: from.z + (to.z - from.z) * t,
      }
    }

    const feedrate = getSegmentFeedrate(seg)
    lines.push({
      d: segmentPath(from, to),
      color: speedToColor(feedrate, speedRange),
      segmentIndex: i,
      feedrate,
      dashed: seg.rapid,
    })
  }

  return lines
}

function toSvgCoords(
  p: Point3,
  viewFrame: ViewFrame,
  svgW: number,
  svgH: number,
  projection: 'xy' | 'xz'
): { cx: number; cy: number } {
  const spanX = viewFrame.maxX - viewFrame.minX
  const spanAxis2 =
    projection === 'xy' ? viewFrame.maxY - viewFrame.minY : viewFrame.maxZ - viewFrame.minZ
  const scaleX = (svgW - SVG_PADDING * 2) / spanX
  const scaleAxis2 = (svgH - SVG_PADDING * 2) / spanAxis2
  const val = projection === 'xy' ? p.y : p.z
  const maxVal = projection === 'xy' ? viewFrame.maxY : viewFrame.maxZ

  return {
    cx: SVG_PADDING + (p.x - viewFrame.minX) * scaleX,
    cy: SVG_PADDING + (maxVal - val) * scaleAxis2,
  }
}

function SvgPanel({
  simulation,
  bedSize,
  viewFrame,
  projection,
  hoveredLine,
  onLineHover,
  animating,
  activeSegmentIndex,
  activeProgress,
  toolheadPos,
}: {
  simulation: SimulationResult
  bedSize: BedSize
  viewFrame: ViewFrame
  projection: 'xy' | 'xz'
  hoveredLine: number | null
  onLineHover: (line: number | null) => void
  animating: boolean
  activeSegmentIndex: number
  activeProgress: number
  toolheadPos: Point3
}) {
  const svgW = 400
  const svgH = projection === 'xy' ? 400 : 200
  const label = projection === 'xy' ? 'Top (XY)' : 'Side (XZ)'
  const axisLabel2 = projection === 'xy' ? 'Y' : 'Z'

  const speedRange = useMemo(() => getSpeedRange(simulation.segments), [simulation.segments])

  const coloredSegments = useMemo(
    () =>
      buildColoredSegmentLines(simulation.segments, viewFrame, svgW, svgH, projection, speedRange),
    [simulation.segments, viewFrame, svgH, projection, speedRange]
  )

  const animatedSegments = useMemo(() => {
    if (!animating || activeSegmentIndex < 0) return null
    return buildColoredSegmentLines(
      simulation.segments,
      viewFrame,
      svgW,
      svgH,
      projection,
      speedRange,
      { upToIndex: activeSegmentIndex, progressOnLast: activeProgress }
    )
  }, [
    animating,
    activeSegmentIndex,
    activeProgress,
    simulation.segments,
    viewFrame,
    svgH,
    projection,
    speedRange,
  ])

  const markerCoords = useMemo(
    () =>
      simulation.markers.map((m) => ({
        ...toSvgCoords(m.position, viewFrame, svgW, svgH, projection),
        marker: m,
      })),
    [simulation.markers, viewFrame, svgH, projection]
  )

  const headCoords = toSvgCoords(toolheadPos, viewFrame, svgW, svgH, projection)

  const highlightedSegs = useMemo(() => {
    if (hoveredLine == null) return ''
    return simulation.segments
      .filter((s) => s.lineNumber === hoveredLine)
      .map((s) => {
        const f = toSvgCoords(s.from, viewFrame, svgW, svgH, projection)
        const t = toSvgCoords(s.to, viewFrame, svgW, svgH, projection)
        return `M${f.cx.toFixed(1)},${f.cy.toFixed(1)} L${t.cx.toFixed(1)},${t.cy.toFixed(1)} `
      })
      .join('')
  }, [hoveredLine, simulation.segments, viewFrame, svgH, projection])

  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-medium text-muted-foreground mb-1">{label}</span>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        className="w-full border rounded bg-background"
        style={{ aspectRatio: `${svgW}/${svgH}` }}
      >
        {/* Bed outline */}
        <rect
          x={SVG_PADDING}
          y={SVG_PADDING}
          width={svgW - SVG_PADDING * 2}
          height={svgH - SVG_PADDING * 2}
          fill="none"
          stroke="currentColor"
          strokeWidth={1}
          className="text-border"
          strokeDasharray="4 2"
        />

        {/* Axis labels */}
        <text
          x={svgW / 2}
          y={svgH - 3}
          textAnchor="middle"
          className="fill-muted-foreground text-[9px]"
        >
          X ({viewFrame.minX === 0 ? `${bedSize.x}mm` : `${viewFrame.minX}..${viewFrame.maxX}`})
        </text>
        <text
          x={5}
          y={svgH / 2}
          textAnchor="middle"
          className="fill-muted-foreground text-[9px]"
          transform={`rotate(-90 5 ${svgH / 2})`}
        >
          {axisLabel2} (
          {projection === 'xy'
            ? viewFrame.minY === 0
              ? `${bedSize.y}mm`
              : `${viewFrame.minY}..${viewFrame.maxY}`
            : viewFrame.minZ === 0
              ? `${bedSize.z}mm`
              : `${viewFrame.minZ}..${viewFrame.maxZ}`}
          )
        </text>

        {/* Full path colored by feedrate (ghost when animating) */}
        {coloredSegments.map((line) => (
          <path
            key={`full-${line.segmentIndex}`}
            d={line.d}
            fill="none"
            stroke={line.color}
            strokeWidth={line.dashed ? 1.5 : 2}
            strokeDasharray={line.dashed ? '4 3' : undefined}
            strokeLinecap="round"
            className={cn(animating && 'opacity-20')}
          />
        ))}

        {/* Progressive animated path (speed-colored) */}
        {animating &&
          animatedSegments?.map((line) => (
            <path
              key={`anim-${line.segmentIndex}`}
              d={line.d}
              fill="none"
              stroke={line.color}
              strokeWidth={line.dashed ? 1.5 : 2.5}
              strokeDasharray={line.dashed ? '4 3' : undefined}
              strokeLinecap="round"
            />
          ))}

        {/* Hovered line highlight */}
        {highlightedSegs && (
          <path
            d={highlightedSegs}
            fill="none"
            stroke="currentColor"
            strokeWidth={3}
            className="text-primary"
          />
        )}

        {/* Hit areas for hover */}
        {simulation.segments.map((seg, idx) => {
          const f = toSvgCoords(seg.from, viewFrame, svgW, svgH, projection)
          const t = toSvgCoords(seg.to, viewFrame, svgW, svgH, projection)
          const feedrate = getSegmentFeedrate(seg)
          return (
            <line
              key={idx}
              x1={f.cx}
              y1={f.cy}
              x2={t.cx}
              y2={t.cy}
              stroke="transparent"
              strokeWidth={8}
              onMouseEnter={() => onLineHover(seg.lineNumber)}
              onMouseLeave={() => onLineHover(null)}
              className="cursor-pointer"
            >
              <title>{`${seg.command} — ${feedrate} mm/min (line ${seg.lineNumber})`}</title>
            </line>
          )
        })}

        {/* Markers */}
        {markerCoords.map(({ cx, cy, marker }, idx) => (
          <g key={idx}>
            <circle
              cx={cx}
              cy={cy}
              r={MARKER_RADIUS}
              fill={MARKER_COLORS[marker.kind] ?? '#888'}
              stroke="white"
              strokeWidth={1}
              onMouseEnter={() => onLineHover(marker.lineNumber)}
              onMouseLeave={() => onLineHover(null)}
              className="cursor-pointer"
            />
            {hoveredLine === marker.lineNumber && (
              <text x={cx + 8} y={cy + 3} className="fill-foreground text-[8px] font-medium">
                {marker.label}
              </text>
            )}
          </g>
        ))}

        {/* Start / end (distinct from speed gradient) */}
        {simulation.segments.length > 0 &&
          (() => {
            const start = toSvgCoords(
              simulation.segments[0].from,
              viewFrame,
              svgW,
              svgH,
              projection
            )
            return (
              <circle
                cx={start.cx}
                cy={start.cy}
                r={3}
                className="fill-sky-500"
                stroke="white"
                strokeWidth={1}
              />
            )
          })()}

        {simulation.segments.length > 0 &&
          (() => {
            const end = toSvgCoords(
              simulation.segments[simulation.segments.length - 1].to,
              viewFrame,
              svgW,
              svgH,
              projection
            )
            return (
              <circle
                cx={end.cx}
                cy={end.cy}
                r={3}
                className="fill-violet-500"
                stroke="white"
                strokeWidth={1}
              />
            )
          })()}

        {/* Animated toolhead */}
        {animating && (
          <circle
            cx={headCoords.cx}
            cy={headCoords.cy}
            r={5}
            className="fill-primary"
            stroke="white"
            strokeWidth={1.5}
          />
        )}
      </svg>
    </div>
  )
}

export function GcodePathPreview({
  gcode,
  appendM400 = false,
  className,
  onLineHover,
}: GcodePathPreviewProps) {
  const [presetId, setPresetId] = useState(DEFAULT_PRESET_ID)
  const [hoveredLine, setHoveredLine] = useState<number | null>(null)

  const bedSize = useMemo(() => {
    const preset = getPresetById(presetId)
    return preset?.size ?? { x: 256, y: 256, z: 256 }
  }, [presetId])

  const viewFrame = useMemo(() => {
    const preset = getPresetById(presetId)
    return preset
      ? getViewFrame(preset)
      : getViewFrame({ id: 'fallback', label: '', size: bedSize })
  }, [presetId, bedSize])

  const simulationOptions = useMemo(() => {
    const preset = getPresetById(presetId)
    return {
      appendM400,
      homePosition: preset?.simulationStart,
    }
  }, [presetId, appendM400])

  const simulation = useMemo(() => {
    if (!gcode.trim()) return null
    return simulateGcode(gcode, simulationOptions)
  }, [gcode, simulationOptions])

  const playback = useGcodePlayback(simulation?.steps ?? [])

  const handleLineHover = useCallback(
    (line: number | null) => {
      setHoveredLine(line)
      onLineHover?.(line)
    },
    [onLineHover]
  )

  const speedRange = useMemo(
    () => getSpeedRange(simulation?.segments ?? []),
    [simulation?.segments]
  )

  if (!simulation || simulation.segments.length === 0) {
    return (
      <div
        className={cn(
          'flex items-center justify-center p-6 text-muted-foreground text-sm border rounded-md',
          className
        )}
      >
        {gcode.trim() ? 'No movement commands found in G-code' : 'Enter G-code to see path preview'}
      </div>
    )
  }

  const animating =
    playback.state === 'playing' || playback.state === 'waiting' || playback.state === 'paused'

  const activeStep =
    playback.position.stepIndex >= 0 ? simulation.steps[playback.position.stepIndex] : null
  const activeSegmentIndex = activeStep?.segmentIndex ?? -1

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {/* Controls bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <select
          value={presetId}
          onChange={(e) => setPresetId(e.target.value)}
          className="h-7 rounded border bg-background px-2 text-xs"
        >
          {BED_PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-1 ml-auto">
          {/* Playback controls */}
          <button
            type="button"
            onClick={playback.stepBackward}
            className="p-1 rounded hover:bg-muted"
            title="Step back"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>

          {playback.state === 'playing' || playback.state === 'waiting' ? (
            <button
              type="button"
              onClick={playback.pause}
              className="p-1 rounded hover:bg-muted"
              title="Pause"
            >
              <Pause className="h-3.5 w-3.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={playback.state === 'paused' ? playback.resume : playback.play}
              className="p-1 rounded hover:bg-muted"
              title="Play"
            >
              <Play className="h-3.5 w-3.5" />
            </button>
          )}

          <button
            type="button"
            onClick={playback.stepForward}
            className="p-1 rounded hover:bg-muted"
            title="Step forward"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={playback.reset}
            className="p-1 rounded hover:bg-muted"
            title="Reset"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          <select
            value={playback.speed}
            onChange={(e) => playback.setSpeed(Number(e.target.value))}
            className="h-7 rounded border bg-background px-1 text-xs ml-1"
          >
            {SPEED_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Scrubber */}
      {simulation.steps.length > 1 && (
        <input
          type="range"
          min={0}
          max={simulation.steps.length - 1}
          value={playback.position.stepIndex < 0 ? 0 : playback.position.stepIndex}
          onChange={(e) => playback.scrubTo(Number(e.target.value))}
          className="w-full h-1.5 accent-primary"
        />
      )}

      {/* Wait label */}
      {playback.position.waitLabel && (
        <div className="text-xs text-amber-600 dark:text-amber-400 text-center font-medium">
          {playback.position.waitLabel}
        </div>
      )}

      {/* SVG panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <SvgPanel
          simulation={simulation}
          bedSize={bedSize}
          viewFrame={viewFrame}
          projection="xy"
          hoveredLine={hoveredLine}
          onLineHover={handleLineHover}
          animating={animating}
          activeSegmentIndex={activeSegmentIndex}
          activeProgress={playback.position.progress}
          toolheadPos={playback.position.position}
        />
        <SvgPanel
          simulation={simulation}
          bedSize={bedSize}
          viewFrame={viewFrame}
          projection="xz"
          hoveredLine={hoveredLine}
          onLineHover={handleLineHover}
          animating={animating}
          activeSegmentIndex={activeSegmentIndex}
          activeProgress={playback.position.progress}
          toolheadPos={playback.position.position}
        />
      </div>

      {/* Legend + info */}
      <div className="flex items-center gap-4 text-[10px] text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-16 rounded-sm border border-border/50"
            style={{
              background: `linear-gradient(to right, rgb(${SPEED_GRADIENT.slow.r},${SPEED_GRADIENT.slow.g},${SPEED_GRADIENT.slow.b}), rgb(${SPEED_GRADIENT.fast.r},${SPEED_GRADIENT.fast.g},${SPEED_GRADIENT.fast.b}))`,
            }}
          />
          <span>Slow ({Math.round(speedRange.min)} mm/min)</span>
          <span>→</span>
          <span>Fast ({Math.round(speedRange.max)} mm/min)</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 border-t-2 border-dashed border-muted-foreground/60" />{' '}
          G0 rapid
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-sky-500" /> Start
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-violet-500" /> End
        </span>
        {simulation.markers.length > 0 && (
          <>
            <span className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-amber-500" /> Home
            </span>
            <span className="flex items-center gap-1">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: MARKER_COLORS.dwell }}
              />{' '}
              Dwell
            </span>
          </>
        )}
        <span className="ml-auto">
          {simulation.segments.length} moves, {simulation.markers.length} events
        </span>
      </div>

      {/* Warnings */}
      {simulation.warnings.length > 0 && (
        <div className="flex items-start gap-2 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 p-2 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <div>
            {simulation.warnings.map((w, i) => (
              <div key={i}>{w}</div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground italic">
        Approximate preview — vendor macros and firmware specifics may affect actual path.
      </p>
    </div>
  )
}

export default GcodePathPreview
