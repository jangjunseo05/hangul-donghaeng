import type { Language } from './types'

/** Any source that can read a text aloud. */
export interface AudioPlayer {
  /** Resolves when playback ends; rejects when this source cannot play. */
  play(text: string, lang: Language, signal: AbortSignal): Promise<void>
  stop(): void
}

export class TtsUnavailable extends Error {
  constructor(public reason: string) { super(reason); this.name = 'TtsUnavailable' }
}

// Female voice names known on common platforms, best first. Names are matched case-insensitively as substrings.
// Unverified on real devices for every OS version; the list only orders the voices a browser already offers.
export const FEMALE_VOICE_HINTS: Record<Language, string[]> = {
  ko: ['sunhi', 'heami', 'yuna', 'sora', 'jimin', 'seoyeon', 'google 한국의', 'ko-kr-standard-a', 'ko-kr-wavenet-a', 'female', '여성'],
  en: ['jenny', 'aria', 'ava', 'samantha', 'allison', 'susan', 'zira', 'karen', 'moira', 'tessa', 'serena', 'google us english', 'female'],
}
export const MALE_VOICE_HINTS = ['male', 'daniel', 'alex', 'fred', 'david', 'mark', 'guy', 'injoon', 'hyunsu', 'aaron', 'tom', 'rishi', '남성']

type VoiceLike = Pick<SpeechSynthesisVoice, 'name' | 'lang' | 'localService' | 'default'>
/** Picks the best voice for a language: female-name hints first, known male names last. */
export function pickVoice<T extends VoiceLike>(voices: readonly T[], lang: Language): T | undefined {
  const prefix = lang === 'ko' ? 'ko' : 'en'
  const candidates = voices.filter(voice => voice.lang.toLowerCase().replace('_', '-').startsWith(prefix))
  if (!candidates.length) return undefined
  const score = (voice: T) => {
    const name = voice.name.toLowerCase()
    const female = FEMALE_VOICE_HINTS[lang].findIndex(hint => name.includes(hint))
    let value = female >= 0 ? 100 - female : 0
    // "male" is a substring of "female": only count it when "female" is absent.
    if (MALE_VOICE_HINTS.some(hint => hint === 'male' ? /(^|[^e])male/.test(name) && !name.includes('female') : name.includes(hint))) value -= 200
    if (lang === 'en' && /en[-_]us/i.test(voice.lang)) value += 3
    if (/natural|neural|enhanced|premium/.test(name)) value += 5
    return value
  }
  return [...candidates].sort((a, b) => score(b) - score(a))[0]
}

/**
 * Splits long text into sentence-sized chunks (≤ max chars) so the first sentence plays sooner and
 * no request exceeds the 600-character TTS limit. Sentence ends: . ! ? … 。 and Korean endings followed by a space.
 */
export function splitForSpeech(text: string, max = 220): string[] {
  const sentences = text.replace(/\s+/g, ' ').trim().match(/[^.!?…。]+(?:[.!?…。]+["'”’)]*|$)\s*/g) ?? []
  const chunks: string[] = []
  for (const raw of sentences) {
    let sentence = raw.trim()
    if (!sentence) continue
    while (sentence.length > max) {
      const cut = Math.max(sentence.lastIndexOf(', ', max), sentence.lastIndexOf(' ', max))
      const at = cut > max / 2 ? cut + 1 : max
      chunks.push(sentence.slice(0, at).trim()); sentence = sentence.slice(at).trim()
    }
    const last = chunks[chunks.length - 1]
    if (last && last.length + sentence.length + 1 <= max / 2) chunks[chunks.length - 1] = last + ' ' + sentence
    else if (sentence) chunks.push(sentence)
  }
  return chunks
}

/** Server-side TTS: POST /api/tts → audio. Any non-OK reply means "use the next source". */
export class ServerTtsPlayer implements AudioPlayer {
  private audio: HTMLAudioElement | null = null
  private url: string | null = null
  private unavailableUntil = 0
  constructor(private endpoint = '/api/tts', private retryAfterMs = 60000) {}
  async play(text: string, lang: Language, signal: AbortSignal) {
    if (Date.now() < this.unavailableUntil) throw new TtsUnavailable('SERVER_TTS_COOLDOWN')
    let response: Response
    try {
      response = await fetch(this.endpoint, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', Accept: 'audio/*' }, body: JSON.stringify({ text, lang }), signal })
    } catch (error) {
      if (signal.aborted) throw error
      this.unavailableUntil = Date.now() + this.retryAfterMs
      throw new TtsUnavailable('SERVER_TTS_OFFLINE')
    }
    const type = response.headers.get('Content-Type') ?? ''
    if (!response.ok || !type.startsWith('audio/')) {
      this.unavailableUntil = Date.now() + this.retryAfterMs
      throw new TtsUnavailable('SERVER_TTS_' + response.status)
    }
    const blob = await response.blob()
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    this.stop()
    this.url = URL.createObjectURL(blob)
    const audio = sharedAudio()
    this.audio = audio
    audio.src = this.url
    await new Promise<void>((resolve, reject) => {
      const done = () => { cleanup(); resolve() }
      const fail = () => { cleanup(); reject(new TtsUnavailable('SERVER_TTS_PLAYBACK')) }
      const abort = () => { cleanup(); audio.pause(); reject(new DOMException('Aborted', 'AbortError')) }
      const cleanup = () => { audio.removeEventListener('ended', done); audio.removeEventListener('error', fail); signal.removeEventListener('abort', abort) }
      audio.addEventListener('ended', done); audio.addEventListener('error', fail); signal.addEventListener('abort', abort, { once: true })
      audio.play().catch(fail)
    })
  }
  stop() {
    this.audio?.pause()
    if (this.url) URL.revokeObjectURL(this.url)
    this.url = null
  }
}

/** Browser speechSynthesis with a female-first voice choice that waits for `voiceschanged`. */
export class BrowserTtsPlayer implements AudioPlayer {
  private voices: SpeechSynthesisVoice[] = []
  private ready: Promise<void> | null = null
  get supported() { return typeof window !== 'undefined' && 'speechSynthesis' in window }
  private loadVoices(): Promise<void> {
    if (this.ready) return this.ready
    this.ready = new Promise(resolve => {
      const synth = window.speechSynthesis
      const read = () => { this.voices = synth.getVoices?.() ?? []; return this.voices.length > 0 }
      if (read()) { resolve(); return }
      const finish = () => { read(); synth.removeEventListener?.('voiceschanged', finish); resolve() }
      synth.addEventListener?.('voiceschanged', finish)
      // Some browsers never fire voiceschanged; fall back to the default voice.
      setTimeout(finish, 800)
    })
    return this.ready
  }
  async play(text: string, lang: Language, signal: AbortSignal) {
    if (!this.supported) throw new TtsUnavailable('BROWSER_TTS_UNSUPPORTED')
    if (!this.voices.length) await this.loadVoices()
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const synth = window.speechSynthesis
    synth.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = lang === 'ko' ? 'ko-KR' : 'en-US'
    const voice = pickVoice(this.voices, lang)
    if (voice) utterance.voice = voice
    utterance.rate = 0.95
    utterance.pitch = 1.05
    await new Promise<void>((resolve, reject) => {
      const abort = () => { synth.cancel(); reject(new DOMException('Aborted', 'AbortError')) }
      signal.addEventListener('abort', abort, { once: true })
      utterance.onend = () => { signal.removeEventListener('abort', abort); resolve() }
      utterance.onerror = event => {
        signal.removeEventListener('abort', abort)
        if (event.error === 'interrupted' || event.error === 'canceled') reject(new DOMException('Aborted', 'AbortError'))
        else reject(new TtsUnavailable('BROWSER_TTS_' + event.error))
      }
      synth.speak(utterance)
    })
  }
  stop() { if (this.supported) window.speechSynthesis.cancel() }
}

/** Tries each player in order; a TtsUnavailable moves to the next one. */
export class FallbackPlayer implements AudioPlayer {
  constructor(private players: AudioPlayer[]) {}
  async play(text: string, lang: Language, signal: AbortSignal) {
    let last: unknown = new TtsUnavailable('NO_PLAYER')
    for (const player of this.players) {
      try { await player.play(text, lang, signal); return }
      catch (error) {
        if (signal.aborted || (error instanceof DOMException && error.name === 'AbortError')) throw error
        last = error
      }
    }
    throw last
  }
  stop() { this.players.forEach(player => player.stop()) }
}

let audioElement: HTMLAudioElement | null = null
function sharedAudio() {
  // One element reused for every clip: iOS keeps the element "unlocked" after the first gesture.
  if (!audioElement) { audioElement = new Audio(); audioElement.preload = 'auto' }
  return audioElement
}
// 0.1 s of silence, used only to unlock audio during the first user gesture.
const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='
export const isIOS = (ua = navigator.userAgent, touch = navigator.maxTouchPoints) => /iP(hone|ad|od)/.test(ua) || (/Macintosh/.test(ua) && touch > 1)
let unlocked = false
/** Call once from a user gesture (pointerdown). iOS otherwise blocks later async playback. */
export function unlockAudio() {
  if (unlocked) return
  unlocked = true
  try { const audio = sharedAudio(); audio.src = SILENCE; void audio.play().catch(() => {}) } catch { /* no audio element */ }
  if (isIOS() && 'speechSynthesis' in window) {
    try { const primer = new SpeechSynthesisUtterance(' '); primer.volume = 0; window.speechSynthesis.speak(primer) } catch { /* not available */ }
  }
}
