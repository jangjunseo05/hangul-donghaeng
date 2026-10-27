import { useEffect, useRef, useState } from 'react'
import type { Language } from './types'
import { BrowserTtsPlayer, FallbackPlayer, ServerTtsPlayer, TtsUnavailable, unlockAudio } from './audio'

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  start(): void; stop(): void; abort(): void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }
export type VoiceSource = 'server' | 'browser' | null
export function useSpeech(language: Language, onTranscript: (text: string) => void) {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [notice, setNotice] = useState('')
  const recognition = useRef<Recognition | null>(null)
  const onTranscriptRef = useRef(onTranscript)
  onTranscriptRef.current = onTranscript
  const server = useRef(new ServerTtsPlayer())
  const browser = useRef(new BrowserTtsPlayer())
  const player = useRef(new FallbackPlayer([server.current, browser.current]))
  const playback = useRef<AbortController | null>(null)
  const supported = Boolean((window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition)
  const canSpeak = 'speechSynthesis' in window || typeof Audio !== 'undefined'
  function stopReading() { playback.current?.abort(); playback.current = null; player.current.stop(); setSpeaking(false) }
  function stopListening() { recognition.current?.stop() }
  function startListening() {
    if (listening) { stopListening(); return }
    setNotice('')
    stopReading()
    const Constructor = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition
    if (!Constructor) { setNotice(language === 'ko' ? '이 브라우저는 음성 입력을 지원하지 않아요. 질문을 입력해 주세요.' : 'Voice input is unavailable in this browser. Please type your question.'); return }
    const next = new Constructor()
    next.lang = language === 'ko' ? 'ko-KR' : 'en-US'
    next.continuous = false
    next.interimResults = true
    next.onresult = event => { const text = Array.from(event.results).map(part => part[0].transcript).join(' '); onTranscriptRef.current(text) }
    next.onend = () => setListening(false)
    next.onerror = event => { setListening(false); if (event.error !== 'aborted') setNotice(language === 'ko' ? '마이크 권한 또는 음성 연결을 확인해 주세요. 텍스트로도 질문할 수 있어요.' : 'Check microphone permission or voice connection. You can also type your question.') }
    recognition.current = next
    try { next.start(); setListening(true) } catch { setListening(false); setNotice(language === 'ko' ? '음성을 시작할 수 없어요. 텍스트를 이용해 주세요.' : 'Could not start voice input. Please use text.') }
  }
  /** Server voice first (POST /api/tts); browser speech when the server voice is unavailable. */
  function read(text: string, lang: Language = language) {
    setNotice('')
    stopReading()
    if (!text.trim()) return
    const controller = new AbortController()
    playback.current = controller
    setSpeaking(true)
    void player.current.play(text, lang, controller.signal).then(() => {
      if (playback.current === controller) { playback.current = null; setSpeaking(false) }
    }, error => {
      if (playback.current !== controller) return
      playback.current = null; setSpeaking(false)
      if (controller.signal.aborted || (error instanceof DOMException && error.name === 'AbortError')) return
      const unsupported = error instanceof TtsUnavailable && error.reason === 'BROWSER_TTS_UNSUPPORTED'
      setNotice(unsupported
        ? (language === 'ko' ? '읽어주기가 지원되지 않아요. 화면의 답변을 확인해 주세요.' : 'Read-aloud is unavailable. Your answer is shown on screen.')
        : (language === 'ko' ? '음성 재생을 확인해 주세요. 텍스트 답변은 유지돼요.' : 'Audio could not play. Your written answer is still available.'))
    })
  }
  useEffect(() => {
    // iOS: unlock audio during the first gesture so later answers can play.
    const unlock = () => { unlockAudio(); window.removeEventListener('pointerdown', unlock) }
    window.addEventListener('pointerdown', unlock)
    return () => { window.removeEventListener('pointerdown', unlock); recognition.current?.abort(); playback.current?.abort(); player.current.stop() }
  }, [])
  return { listening, speaking, supported, canSpeak, notice, startListening, stopListening, read, stopReading }
}
