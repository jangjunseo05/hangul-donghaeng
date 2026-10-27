import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { GATE_SIZE, SceneGate, toGrey } from './autoCompanion'

export const GATE_SAMPLE_MS = 500
/** Samples the live preview locally (32×32 grey, nothing is sent) to decide when a frame is worth sending. */
export function useSceneGate(video: RefObject<HTMLVideoElement | null>, enabled: boolean, sampling: boolean, onSceneChange: () => void) {
  const gate = useRef(new SceneGate())
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const changeCallback = useRef(onSceneChange)
  changeCallback.current = onSceneChange
  const wasChanged = useRef(false)
  function sample() {
    const element = video.current
    if (!element || element.readyState < 2 || !element.videoWidth) return false
    if (!canvas.current) { canvas.current = document.createElement('canvas'); canvas.current.width = GATE_SIZE; canvas.current.height = GATE_SIZE }
    const context = canvas.current.getContext('2d', { willReadFrequently: true })
    if (!context) return false
    try {
      context.drawImage(element, 0, 0, GATE_SIZE, GATE_SIZE)
      const state = gate.current.sample(toGrey(context.getImageData(0, 0, GATE_SIZE, GATE_SIZE).data), Date.now())
      if (state.ready && !wasChanged.current) changeCallback.current()
      wasChanged.current = state.ready
      return true
    } catch { return false }
  }
  useEffect(() => {
    if (!enabled || !sampling) return
    sample()
    const timer = window.setInterval(sample, GATE_SAMPLE_MS)
    return () => clearInterval(timer)
  }, [enabled, sampling])
  // Pauses keep the last sent frame; turning automatic mode off forgets it.
  useEffect(() => { if (!enabled) { gate.current.reset(); wasChanged.current = false } }, [enabled])
  return {
    /** Ready means: changed since the last sent frame, held steady, not blurry. Fails open when sampling is impossible. */
    ready: () => sample() ? gate.current.state(Date.now()).ready : true,
    /** Snapshot before sending; pass it to markSent only after the send succeeded. */
    current: () => gate.current.current(),
    markSent: (frame: Uint8Array | null) => { gate.current.markSent(frame); wasChanged.current = false },
  }
}
