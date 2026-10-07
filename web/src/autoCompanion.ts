export const OBSERVATION_INTERVAL_MS = 20000
export const INITIAL_OBSERVATION_DELAY_MS = 3000

/** At most one automatic task; next interval starts after that task settles. */
export class FrameScheduler {
  private enabled = false
  private paused = false
  private inFlight = false
  private disposed = false
  private generation = 0
  private firstObservation = true
  private timer: ReturnType<typeof setTimeout> | null = null
  constructor(private observe: (current: () => boolean) => Promise<void>, private onError: () => void = () => {}) {}
  setState(enabled: boolean, paused: boolean) {
    if (this.enabled === enabled && this.paused === paused) return
    if (enabled && !this.enabled) this.firstObservation = true
    this.enabled = enabled; this.paused = paused
    this.interrupt()
  }
  interrupt() {
    this.generation += 1
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
    this.schedule()
  }
  dispose() { this.disposed = true; this.interrupt() }
  private schedule() {
    if (this.disposed || !this.enabled || this.paused || this.inFlight || this.timer !== null) return
    this.timer = setTimeout(() => { this.timer = null; void this.tick() }, this.firstObservation ? INITIAL_OBSERVATION_DELAY_MS : OBSERVATION_INTERVAL_MS)
  }
  private async tick() {
    if (this.disposed || !this.enabled || this.paused || this.inFlight) return
    this.firstObservation = false
    this.inFlight = true
    const version = this.generation
    try { await this.observe(() => !this.disposed && this.enabled && !this.paused && this.generation === version) }
    catch { this.onError() }
    finally { this.inFlight = false; this.schedule() }
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
