import { useEffect, useRef, useState } from 'react'
import type { Language } from './types'

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  start(): void; stop(): void; abort(): void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }
export function useSpeech(language: Language, onTranscript: (text: string) => void) {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [notice, setNotice] = useState('')
  const recognition = useRef<Recognition | null>(null)
  const onTranscriptRef = useRef(onTranscript)
  onTranscriptRef.current = onTranscript
  const supported = Boolean((window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition)
  const canSpeak = 'speechSynthesis' in window
  function stopReading() { if (canSpeak) window.speechSynthesis.cancel(); setSpeaking(false) }
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
  function read(text: string, lang: Language = language) {
    setNotice('')
    if (!canSpeak) { setNotice(language === 'ko' ? '읽어주기가 지원되지 않아요. 화면의 답변을 확인해 주세요.' : 'Read-aloud is unavailable. Your answer is shown on screen.'); return }
    stopReading()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = lang === 'ko' ? 'ko-KR' : 'en-US'
    const voice = window.speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith(lang))
    if (voice) utterance.voice = voice
    utterance.rate = 0.95
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = event => { setSpeaking(false); if (event.error !== 'interrupted' && event.error !== 'canceled') setNotice(language === 'ko' ? '음성 재생을 확인해 주세요. 텍스트 답변은 유지돼요.' : 'Audio could not play. Your written answer is still available.') }
    setSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }
  useEffect(() => () => { recognition.current?.abort(); if ('speechSynthesis' in window) window.speechSynthesis.cancel() }, [])
  return { listening, speaking, supported, canSpeak, notice, startListening, stopListening, read, stopReading }
}
