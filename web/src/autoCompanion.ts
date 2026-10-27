export const OBSERVATION_INTERVAL_MS = 20000
export const INITIAL_OBSERVATION_DELAY_MS = 3000
/** Scene change after a settled answer may bring the next frame forward to this. */
export const SCENE_CHANGE_INTERVAL_MS = 8000
/** A frame the scene gate rejected is re-checked this soon; it does not count as an attempt. */
export const GATE_RETRY_MS = 1000
export const MAX_QUIET_INTERVAL_MS = 120000
export const MAX_CONSECUTIVE_FAILURES = 3

/**
 * Outcome of one automatic observation.
 * shown: an answer was displayed. quiet: nothing cultural to suggest.
 * skipped: the scene gate held the frame back (no request was sent). error: a transient failure.
 */
export type ObserveOutcome = 'shown' | 'quiet' | 'skipped' | 'error'

/** Adaptive delay after an outcome (backend report §2-2 B). */
export function nextObservationDelay(outcome: ObserveOutcome | undefined, quietStreak: number, failureStreak: number) {
  if (outcome === 'skipped') return GATE_RETRY_MS
  if (outcome === 'quiet') return Math.min(OBSERVATION_INTERVAL_MS * 2 ** Math.max(0, quietStreak - 1), MAX_QUIET_INTERVAL_MS)
  if (outcome === 'error') return Math.min(OBSERVATION_INTERVAL_MS * 2 ** Math.max(0, failureStreak - 1), MAX_QUIET_INTERVAL_MS)
  return OBSERVATION_INTERVAL_MS
}

/** At most one automatic task; next interval starts after that task settles. */
export class FrameScheduler {
  private enabled = false
  private paused = false
  private inFlight = false
  private disposed = false
  private generation = 0
  private firstObservation = true
  private retry = false
  private timer: ReturnType<typeof setTimeout> | null = null
  private delay = OBSERVATION_INTERVAL_MS
  private settledAt = 0
  private quietStreak = 0
  private failureStreak = 0
  constructor(private observe: (current: () => boolean) => Promise<ObserveOutcome | void>, private onError: () => void = () => {}) {}
  setState(enabled: boolean, paused: boolean) {
    if (this.enabled === enabled && this.paused === paused) return
    if (enabled && !this.enabled) { this.firstObservation = true; this.quietStreak = 0; this.failureStreak = 0; this.delay = OBSERVATION_INTERVAL_MS }
    this.enabled = enabled; this.paused = paused
    this.interrupt()
  }
  interrupt() {
    this.generation += 1
    this.retry = false
    this.clearTimer()
    this.schedule()
  }
  /** The scene changed meaningfully: reset the quiet backoff and allow an earlier frame. */
  notifySceneChange() {
    if (this.disposed || !this.enabled || this.paused || this.inFlight || this.firstObservation || this.retry) return
    this.quietStreak = 0
    if (this.delay <= SCENE_CHANGE_INTERVAL_MS) return
    this.delay = SCENE_CHANGE_INTERVAL_MS
    this.clearTimer()
    this.schedule(Math.max(0, this.settledAt + SCENE_CHANGE_INTERVAL_MS - Date.now()))
  }
  dispose() { this.disposed = true; this.interrupt() }
  private clearTimer() {
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
  }
  private schedule(wait = this.retry ? GATE_RETRY_MS : this.firstObservation ? INITIAL_OBSERVATION_DELAY_MS : this.delay) {
    if (this.disposed || !this.enabled || this.paused || this.inFlight || this.timer !== null) return
    this.timer = setTimeout(() => { this.timer = null; void this.tick() }, wait)
  }
  private async tick() {
    if (this.disposed || !this.enabled || this.paused || this.inFlight) return
    this.inFlight = true
    const version = this.generation
    let outcome: ObserveOutcome | void = undefined
    try { outcome = await this.observe(() => !this.disposed && this.enabled && !this.paused && this.generation === version) }
    catch { outcome = 'error' }
    finally {
      this.inFlight = false
      if (outcome === 'skipped') this.retry = true
      else {
        this.retry = false
        this.firstObservation = false
        if (outcome === 'quiet') this.quietStreak += 1
        else if (outcome === 'shown') this.quietStreak = 0
        this.failureStreak = outcome === 'error' ? this.failureStreak + 1 : 0
        this.delay = nextObservationDelay(outcome ?? undefined, this.quietStreak, this.failureStreak)
        this.settledAt = Date.now()
      }
      if (this.failureStreak >= MAX_CONSECUTIVE_FAILURES) { this.failureStreak = 0; this.onError() }
      this.schedule()
    }
  }
}

export const normalizedSpeech = (text: string) => text.normalize('NFC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')

/** Repeated automatic suggestions stay visible but are not spoken repeatedly. */
export class ObservationSpeechGuard {
  private heard = new Set<string>()
  reset() { this.heard.clear() }
  shouldRead(text: string, suggestionIds: string[]) {
    const key = suggestionIds.length ? `suggest:${[...new Set(suggestionIds)].sort().join('|')}` : `text:${normalizedSpeech(text)}`
    if (this.heard.has(key)) return false
    this.heard.add(key)
    if (this.heard.size > 30) this.heard.delete(this.heard.values().next().value!)
    return true
  }
}

// ── Scene change gate (backend report §2-2 A) ─────────────────────────────
export const GATE_SIZE = 32
/** Mean absolute grey difference (0–255) that counts as a new scene. */
export const T_CHANGE = 18
/** Mean absolute difference between consecutive samples that counts as "holding still". */
export const T_STABLE = 6
export const STABLE_MS = 1200
/** Laplacian variance below this is blurry, but only for frames that have texture. */
export const T_SHARP = 40
/** Frames whose grey standard deviation is below this have no texture to judge sharpness on. */
export const LOW_TEXTURE_STD = 4

export function meanAbsDiff(a: Uint8Array, b: Uint8Array) {
  let sum = 0
  for (let i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i])
  return sum / a.length
}
export function greyStd(frame: Uint8Array) {
  let sum = 0, square = 0
  for (const value of frame) { sum += value; square += value * value }
  const mean = sum / frame.length
  return Math.sqrt(Math.max(0, square / frame.length - mean * mean))
}
/** Variance of a 4-neighbour Laplacian on a square grey frame. */
export function laplacianVariance(frame: Uint8Array, size = GATE_SIZE) {
  const values: number[] = []
  for (let y = 1; y < size - 1; y++) for (let x = 1; x < size - 1; x++) {
    const i = y * size + x
    values.push(frame[i - size] + frame[i + size] + frame[i - 1] + frame[i + 1] - 4 * frame[i])
  }
  const mean = values.reduce((a, b) => a + b, 0) / values.length
  return values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length
}
export function isSharpEnough(frame: Uint8Array, size = GATE_SIZE) {
  return greyStd(frame) < LOW_TEXTURE_STD || laplacianVariance(frame, size) >= T_SHARP
}
/** Converts RGBA pixels (canvas ImageData) to a grey frame. */
export function toGrey(rgba: Uint8ClampedArray | Uint8Array) {
  const grey = new Uint8Array(rgba.length / 4)
  for (let i = 0; i < grey.length; i++) grey[i] = Math.round(0.299 * rgba[i * 4] + 0.587 * rgba[i * 4 + 1] + 0.114 * rgba[i * 4 + 2])
  return grey
}

export type GateState = { ready: boolean; changed: boolean; stable: boolean; sharp: boolean }
/**
 * Decides whether the current preview is worth sending.
 * A frame is ready when it differs from the last sent frame (or nothing was sent yet),
 * the camera has been held still for STABLE_MS, and the frame is not blurry.
 */
export class SceneGate {
  private previous: Uint8Array | null = null
  private sent: Uint8Array | null = null
  private stableSince: number | null = null
  private latest: Uint8Array | null = null
  reset() { this.previous = null; this.sent = null; this.stableSince = null; this.latest = null }
  sample(frame: Uint8Array, now: number): GateState {
    const still = this.previous !== null && meanAbsDiff(frame, this.previous) < T_STABLE
    if (!still) this.stableSince = now
    this.previous = frame
    this.latest = frame
    return this.state(now)
  }
  state(now: number): GateState {
    if (!this.latest) return { ready: false, changed: false, stable: false, sharp: false }
    const changed = this.sent === null || meanAbsDiff(this.latest, this.sent) > T_CHANGE
    const stable = this.stableSince !== null && now - this.stableSince >= STABLE_MS
    const sharp = isSharpEnough(this.latest)
    return { ready: changed && stable && sharp, changed, stable, sharp }
  }
  /** The frame the gate would send now (to mark later, once the send succeeded). */
  current() { return this.latest }
  markSent(frame: Uint8Array | null = this.latest) { if (frame) this.sent = frame }
}
