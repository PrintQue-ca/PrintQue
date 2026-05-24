import { describe, expect, it } from 'vitest'
import { simulateGcode } from '../../lib/gcode-simulator'
import { getSegmentFeedrate, getSpeedRange, speedToColor } from '../../lib/gcode-speed'

describe('simulateGcode', () => {
  it('returns empty result for blank input', () => {
    const result = simulateGcode('')
    expect(result.segments).toHaveLength(0)
    expect(result.markers).toHaveLength(0)
    expect(result.steps).toHaveLength(0)
    expect(result.warnings).toHaveLength(0)
  })

  it('parses G0 rapid move in absolute mode', () => {
    const result = simulateGcode('G0 X100 Y200 Z10')
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0].rapid).toBe(true)
    expect(result.segments[0].from).toEqual({ x: 0, y: 0, z: 0 })
    expect(result.segments[0].to).toEqual({ x: 100, y: 200, z: 10 })
  })

  it('parses G1 feed move', () => {
    const result = simulateGcode('G1 X50 Y50 F1500')
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0].rapid).toBe(false)
    expect(result.segments[0].to).toEqual({ x: 50, y: 50, z: 0 })
  })

  it('handles G90/G91 absolute/relative toggling', () => {
    const gcode = ['G90', 'G0 X10 Y10', 'G91', 'G0 X5 Y5', 'G90', 'G0 X0 Y0'].join('\n')

    const result = simulateGcode(gcode)
    expect(result.segments).toHaveLength(3)
    expect(result.segments[0].to).toEqual({ x: 10, y: 10, z: 0 })
    expect(result.segments[1].to).toEqual({ x: 15, y: 15, z: 0 })
    expect(result.segments[2].to).toEqual({ x: 0, y: 0, z: 0 })
  })

  it('handles G28 homing', () => {
    const gcode = 'G0 X100 Y100\nG28 X Y'
    const result = simulateGcode(gcode)

    expect(result.segments).toHaveLength(1)
    expect(result.markers).toHaveLength(1)
    expect(result.markers[0].kind).toBe('home')
    expect(result.markers[0].position).toEqual({ x: 0, y: 0, z: 0 })
  })

  it('homes all axes when no axis specified', () => {
    const result = simulateGcode('G0 X10 Y20 Z30\nG28')
    expect(result.markers[0].position).toEqual({ x: 0, y: 0, z: 0 })
    expect(result.markers[0].label).toBe('Home XYZ')
  })

  it('handles G92 set position', () => {
    const gcode = 'G92 X10 Y20 Z5\nG0 X20'
    const result = simulateGcode(gcode)

    expect(result.markers).toHaveLength(1)
    expect(result.markers[0].kind).toBe('set_position')
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0].from).toEqual({ x: 10, y: 20, z: 5 })
    expect(result.segments[0].to).toEqual({ x: 20, y: 20, z: 5 })
  })

  it('handles G4 dwell with P (milliseconds)', () => {
    const result = simulateGcode('G4 P2000')
    expect(result.markers).toHaveLength(1)
    expect(result.markers[0].kind).toBe('dwell')
    expect(result.steps[0].durationMs).toBe(2000)
  })

  it('handles G4 dwell with S (seconds)', () => {
    const result = simulateGcode('G4 S3')
    expect(result.markers).toHaveLength(1)
    expect(result.steps[0].durationMs).toBe(3000)
  })

  it('handles G21 millimeter units without unsupported warning', () => {
    const result = simulateGcode('G21\nG0 X10')
    expect(result.warnings).toHaveLength(0)
    expect(result.segments[0].to.x).toBe(10)
  })

  it('handles M400 sync marker', () => {
    const result = simulateGcode('G0 X10\nM400')
    expect(result.markers).toHaveLength(1)
    expect(result.markers[0].kind).toBe('sync')
  })

  it('handles M109/M190 temperature waits', () => {
    const result = simulateGcode('M109 S210\nM190 S60')
    expect(result.markers).toHaveLength(2)
    expect(result.markers[0].kind).toBe('wait_temp')
    expect(result.markers[0].label).toBe('Wait nozzle 210°C')
    expect(result.markers[1].label).toBe('Wait bed 60°C')
  })

  it('handles M0/M1 stop markers', () => {
    const result = simulateGcode('M0\nM1')
    expect(result.markers).toHaveLength(2)
    expect(result.markers[0].kind).toBe('stop')
    expect(result.markers[0].label).toBe('Stop')
    expect(result.markers[1].label).toBe('Optional stop')
  })

  it('strips comments before parsing', () => {
    const gcode = '; This is a comment\nG0 X10 ; inline comment\n; Another comment'
    const result = simulateGcode(gcode)
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0].to.x).toBe(10)
  })

  it('skips empty lines', () => {
    const gcode = '\n\nG0 X10\n\n'
    const result = simulateGcode(gcode)
    expect(result.segments).toHaveLength(1)
  })

  it('does not create a segment when no axis changes', () => {
    const result = simulateGcode('G0 F3000')
    expect(result.segments).toHaveLength(0)
  })

  it('appends M400 when appendM400 is true and not present', () => {
    const result = simulateGcode('G0 X10', { appendM400: true })
    const syncMarkers = result.markers.filter((m) => m.kind === 'sync')
    expect(syncMarkers).toHaveLength(1)
  })

  it('does not duplicate M400 when appendM400 is true and already present', () => {
    const result = simulateGcode('G0 X10\nM400', { appendM400: true })
    const syncMarkers = result.markers.filter((m) => m.kind === 'sync')
    expect(syncMarkers).toHaveLength(1)
  })

  it('uses custom home position', () => {
    const result = simulateGcode('G28', { homePosition: { x: 256, y: 256, z: 0 } })
    expect(result.markers[0].position).toEqual({ x: 256, y: 256, z: 0 })
  })

  it('computes bounds from all points', () => {
    const result = simulateGcode('G0 X100 Y200\nG0 X-10 Y0')
    expect(result.bounds.min.x).toBe(-10)
    expect(result.bounds.max.x).toBe(100)
    expect(result.bounds.min.y).toBe(0)
    expect(result.bounds.max.y).toBe(200)
  })

  it('warns on unsupported G-commands', () => {
    const result = simulateGcode('G5 X10')
    expect(result.warnings).toHaveLength(1)
    expect(result.warnings[0]).toContain('G5')
  })

  it('silently ignores M and T commands', () => {
    const result = simulateGcode('M84\nT0\nM104 S200')
    expect(result.warnings).toHaveLength(0)
    expect(result.segments).toHaveLength(0)
  })

  it('handles G2 clockwise arc', () => {
    const gcode = 'G0 X10 Y0\nG2 X0 Y10 I-10 J0'
    const result = simulateGcode(gcode)
    expect(result.segments.length).toBeGreaterThan(1)
  })

  it('handles G3 counter-clockwise arc', () => {
    const gcode = 'G0 X10 Y0\nG3 X0 Y10 I-10 J0'
    const result = simulateGcode(gcode)
    expect(result.segments.length).toBeGreaterThan(1)
  })

  it('generates steps for all moves and markers', () => {
    const gcode = 'G28\nG0 X100\nG4 S1\nG1 Y200\nM400'
    const result = simulateGcode(gcode)
    expect(result.steps.length).toBe(5)
    expect(result.steps[0].kind).toBe('home')
    expect(result.steps[1].kind).toBe('move')
    expect(result.steps[2].kind).toBe('dwell')
    expect(result.steps[3].kind).toBe('move')
    expect(result.steps[4].kind).toBe('sync')
  })

  it('calculates move duration from feedrate', () => {
    const result = simulateGcode('G1 X60 F3600')
    expect(result.steps[0].durationMs).toBeCloseTo(1000, 0)
  })

  it('maps slow feedrate to green and fast to red', () => {
    const range = { min: 500, max: 6000 }
    expect(speedToColor(500, range)).toBe('rgb(34,197,94)')
    expect(speedToColor(6000, range)).toBe('rgb(239,68,68)')
  })

  it('computes speed range from segments', () => {
    const result = simulateGcode('G1 X10 F500\nG0 X20')
    const range = getSpeedRange(result.segments)
    expect(range.min).toBe(500)
    expect(range.max).toBe(6000)
    expect(getSegmentFeedrate(result.segments[0])).toBe(500)
    expect(getSegmentFeedrate(result.segments[1])).toBe(6000)
  })

  it('simulates a typical ejection script', () => {
    const gcode = [
      '; Ejection sequence',
      'G90',
      'G28 X Y',
      'G0 Z5 F600',
      'G0 X256 Y256 F6000',
      'G1 Y0 F3000',
      'G28 X Y',
      'M400',
    ].join('\n')

    const result = simulateGcode(gcode)
    expect(result.segments.length).toBeGreaterThanOrEqual(3)
    expect(result.markers.filter((m) => m.kind === 'home')).toHaveLength(2)
    expect(result.markers.filter((m) => m.kind === 'sync')).toHaveLength(1)
    expect(result.warnings).toHaveLength(0)
  })
})
