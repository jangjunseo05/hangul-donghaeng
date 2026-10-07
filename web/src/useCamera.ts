import { useEffect, useRef, useState } from 'react'
import type { Language } from './types'

export type CameraPhase = 'idle' | 'starting' | 'live'

export function useCamera(language: Language) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const generation = useRef(0)
  const [phase, setPhase] = useState<CameraPhase>('idle')
  const [notice, setNotice] = useState('')
  const languageRef = useRef(language)
  languageRef.current = language
  const message = (en: string, ko: string) => languageRef.current === 'ko' ? ko : en
  const isHidden = () => document.visibilityState === 'hidden'

  function release() {
    generation.current += 1
    for (const track of stream.current?.getTracks() ?? []) { track.onended = null; track.stop() }
    stream.current = null
    if (videoRef.current) { videoRef.current.pause(); videoRef.current.srcObject = null }
  }
  function stop() { release(); setPhase('idle') }
  async function start() {
    release()
    setNotice('')
    if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
      setNotice(message('Camera preview is unavailable here. Use HTTPS or localhost, or choose a photo.', '카메라 미리보기를 사용할 수 없어요. HTTPS·localhost에서 열거나 사진을 선택해 주세요.'))
      setPhase('idle'); return
    }
    const version = generation.current
    setPhase('starting')
    try {
      const next = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      if (generation.current !== version || isHidden()) { next.getTracks().forEach(track => track.stop()); return }
      stream.current = next
      next.getVideoTracks().forEach(track => { track.onended = () => { stop(); setNotice(message('Camera access ended. You can start it again or choose a photo.', '카메라 연결이 끝났어요. 다시 시작하거나 사진을 선택해 주세요.')) } })
      setPhase('live')
    } catch (error) {
      if (generation.current !== version) return
      setPhase('idle')
      const denied = error instanceof DOMException && ['NotAllowedError', 'SecurityError'].includes(error.name)
      setNotice(denied
        ? message('Camera permission was not granted. You can still choose a photo and ask a question.', '카메라 권한을 받지 못했어요. 사진을 선택해 질문할 수 있어요.')
        : message('The camera could not start. Check that it is available, or choose a photo.', '카메라를 시작할 수 없어요. 다른 앱의 사용 여부를 확인하거나 사진을 선택해 주세요.'))
    }
  }
  async function capture(): Promise<File | null> {
    const video = videoRef.current
    const version = generation.current
    if (!stream.current || !video || video.readyState < 2 || !video.videoWidth || isHidden()) {
      setNotice(message('Wait for the camera preview before capturing.', '미리보기가 보이면 촬영해 주세요.')); return null
    }
    const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    try {
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Canvas unavailable')
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85))
      if (generation.current !== version || !stream.current || isHidden()) return null
      if (!blob) throw new Error('Frame unavailable')
      setNotice('')
      return new File([blob], `camera-frame-${Date.now()}.jpg`, { type: 'image/jpeg' })
    } catch {
      if (generation.current === version) setNotice(message('This frame could not be captured. Please choose a photo instead.', '사진을 담지 못했어요. 사진 선택을 이용해 주세요.'))
      return null
    }
  }
  useEffect(() => {
    if (phase !== 'live' || !videoRef.current || !stream.current) return
    const version = generation.current
    videoRef.current.srcObject = stream.current
    void videoRef.current.play().catch(() => { if (generation.current === version && stream.current) setNotice(message('Tap the preview to play it, then capture a photo.', '미리보기를 눌러 재생한 뒤 촬영해 주세요.')) })
  }, [phase])
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        stop()
        setNotice(message('Camera stopped when you left this page. Start it again when you are ready.', '다른 화면으로 이동해 카메라를 껐어요. 필요할 때 다시 시작해 주세요.'))
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { document.removeEventListener('visibilitychange', onVisibility); release() }
  }, [])
  return { videoRef, phase, notice, start, stop, capture, isLive: () => Boolean(stream.current?.getVideoTracks().some(track => track.readyState === 'live')) }
}
