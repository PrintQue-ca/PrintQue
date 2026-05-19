import { useCallback, useEffect, useRef, useState } from 'react'
import type { Point3, SimulationStep } from '@/lib/gcode-simulator'

export type PlaybackState = 'idle' | 'playing' | 'paused' | 'waiting'

export interface PlaybackPosition {
  stepIndex: number
  progress: number
  position: Point3
  activeLineNumber: number | null
  waitLabel: string | null
}

const MAX_DWELL_DISPLAY_MS = 5000

function lerp3(a: Point3, b: Point3, t: number): Point3 {
  return {
    x: a.x + (b.x - a.x) * t,
    y: a.y + (b.y - a.y) * t,
    z: a.z + (b.z - a.z) * t,
  }
}

export function useGcodePlayback(steps: SimulationStep[]) {
  const [state, setState] = useState<PlaybackState>('idle')
  const [stepIndex, setStepIndex] = useState(-1)
  const [progress, setProgress] = useState(0)
  const [speed, setSpeed] = useState(1)

  const stateRef = useRef(state)
  const stepIndexRef = useRef(stepIndex)
  const progressRef = useRef(progress)
  const speedRef = useRef(speed)
  const animFrameRef = useRef<number | null>(null)
  const lastTimeRef = useRef<number>(0)
  const waitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  stateRef.current = state
  stepIndexRef.current = stepIndex
  progressRef.current = progress
  speedRef.current = speed

  const cleanup = useCallback(() => {
    if (animFrameRef.current != null) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    if (waitTimerRef.current != null) {
      clearTimeout(waitTimerRef.current)
      waitTimerRef.current = null
    }
  }, [])

  useEffect(() => cleanup, [cleanup])

  const advanceToStep = useCallback(
    (idx: number) => {
      if (idx < 0 || idx >= steps.length) {
        cleanup()
        setState('idle')
        setStepIndex(steps.length - 1)
        setProgress(1)
        return
      }

      setStepIndex(idx)
      setProgress(0)

      const step = steps[idx]

      if (step.kind === 'move') {
        setState('playing')
        lastTimeRef.current = performance.now()

        const baseDuration = step.durationMs ?? 500
        const duration = Math.max(baseDuration / speedRef.current, 50)

        const animate = (now: number) => {
          if (stateRef.current !== 'playing') return

          const elapsed = now - lastTimeRef.current
          const newProgress = Math.min(elapsed / duration, 1)
          setProgress(newProgress)

          if (newProgress >= 1) {
            advanceToStep(stepIndexRef.current + 1)
          } else {
            animFrameRef.current = requestAnimationFrame(animate)
          }
        }

        animFrameRef.current = requestAnimationFrame(animate)
      } else if (step.kind === 'dwell' && step.durationMs != null && step.durationMs > 0) {
        setState('waiting')
        const cappedMs = Math.min(step.durationMs / speedRef.current, MAX_DWELL_DISPLAY_MS)
        waitTimerRef.current = setTimeout(() => {
          if (stateRef.current === 'waiting') {
            advanceToStep(stepIndexRef.current + 1)
          }
        }, cappedMs)
      } else if (step.kind === 'wait_temp' || step.kind === 'sync' || step.kind === 'stop') {
        setState('waiting')
        waitTimerRef.current = setTimeout(() => {
          if (stateRef.current === 'waiting') {
            advanceToStep(stepIndexRef.current + 1)
          }
        }, 800 / speedRef.current)
      } else {
        // home, set_position — instant
        advanceToStep(idx + 1)
      }
    },
    [steps, cleanup]
  )

  const play = useCallback(() => {
    cleanup()
    if (stepIndex < 0 || stepIndex >= steps.length - 1) {
      advanceToStep(0)
    } else {
      advanceToStep(stepIndex)
    }
  }, [stepIndex, steps.length, advanceToStep, cleanup])

  const pause = useCallback(() => {
    cleanup()
    setState('paused')
  }, [cleanup])

  const resume = useCallback(() => {
    if (state === 'paused' || state === 'waiting') {
      advanceToStep(stepIndex)
    }
  }, [state, stepIndex, advanceToStep])

  const reset = useCallback(() => {
    cleanup()
    setState('idle')
    setStepIndex(-1)
    setProgress(0)
  }, [cleanup])

  const stepForward = useCallback(() => {
    cleanup()
    const next = Math.min(stepIndex + 1, steps.length - 1)
    setStepIndex(next)
    setProgress(1)
    setState('paused')
  }, [stepIndex, steps.length, cleanup])

  const stepBackward = useCallback(() => {
    cleanup()
    const prev = Math.max(stepIndex - 1, 0)
    setStepIndex(prev)
    setProgress(1)
    setState('paused')
  }, [stepIndex, cleanup])

  const scrubTo = useCallback(
    (idx: number) => {
      cleanup()
      const clamped = Math.max(0, Math.min(idx, steps.length - 1))
      setStepIndex(clamped)
      setProgress(1)
      setState('paused')
    },
    [steps.length, cleanup]
  )

  const currentStep = stepIndex >= 0 && stepIndex < steps.length ? steps[stepIndex] : null

  const position: PlaybackPosition = {
    stepIndex,
    progress,
    position: currentStep
      ? lerp3(currentStep.from, currentStep.to, progress)
      : { x: 0, y: 0, z: 0 },
    activeLineNumber: currentStep?.lineNumber ?? null,
    waitLabel: state === 'waiting' && currentStep ? currentStep.label : null,
  }

  return {
    state,
    position,
    speed,
    setSpeed,
    play,
    pause,
    resume,
    reset,
    stepForward,
    stepBackward,
    scrubTo,
    totalSteps: steps.length,
  }
}
