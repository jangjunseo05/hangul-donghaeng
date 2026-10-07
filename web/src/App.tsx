import { useEffect, useRef, useState } from 'react'
import { ArrowRight, ArrowUpRight, BookOpen, Camera, Check, ChevronDown, Compass, Copy, Download, Globe2, ImagePlus, Info, LoaderCircle, MapPin, Mic, Navigation, RotateCcw, ShieldCheck, Sparkles, Square, Utensils, Volume2, VolumeX, WifiOff, X } from 'lucide-react'
import MapView, { SEOCHON } from './MapView'
import { api, ApiError, safeSourceUrl, waitForResult } from './api'
import { useSpeech } from './useSpeech'
import { useCamera } from './useCamera'
import CameraPanel from './CameraPanel'
import { useAutoCompanion } from './useAutoCompanion'
import { ObservationSpeechGuard } from './autoCompanion'
import type { Catalog, CatalogPlace, DatasetMode, Evidence, GuideResult, Health, InteractionMode, Language, Location, Place, Radius } from './types'

type Phase = 'idle' | 'uploading' | 'submitting' | 'queued' | 'running' | 'ready' | 'need_confirmation' | 'failed'
type SubmitOptions = { question?: string; food?: string | null; shop?: string | null; place?: string | null; radius?: Radius; location?: Location; frame?: File; interaction?: InteractionMode; valid?: () => boolean }
const EMPTY_PLACES: Place[] = []

export default function App() {
  const [language, setLanguage] = useState<Language>('en')
  const t = (en: string, ko: string) => language === 'ko' ? ko : en
  const [session, setSession] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthFailed, setHealthFailed] = useState(false)
  const [checkedAt, setCheckedAt] = useState<string | null>(null)
  const [statusOpen, setStatusOpen] = useState(false)
  const [mode, setMode] = useState<DatasetMode>('real_place')
  const [question, setQuestion] = useState('')
  const [photo, setPhoto] = useState<{ file: File; url: string; id: string | null } | null>(null)
  const [photoLocked, setPhotoLocked] = useState(false)
  const photoLockedRef = useRef(false)
  const [photoNotice, setPhotoNotice] = useState('')
  const [location, setLocation] = useState<Location | null>(null)
  const [demoLocation, setDemoLocation] = useState(false)
  const [radius, setRadius] = useState<Radius>(1000)
  const [locating, setLocating] = useState(false)
  const [locationNotice, setLocationNotice] = useState('')
  const [result, setResult] = useState<GuideResult | null>(null)
  const [stale, setStale] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState('')
  const [copyNotice, setCopyNotice] = useState('')
  const [autoRead, setAutoRead] = useState(true)
  const autoReadRef = useRef(autoRead)
  autoReadRef.current = autoRead
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogFailed, setCatalogFailed] = useState(false)
  const [anchor, setAnchor] = useState<CatalogPlace | null>(null)
  // Search origin survives scene changes; explicit photo identity does not.
  const identityPlace = useRef<string | null>(null)
  const [automatic, setAutomatic] = useState(false)
  const [automaticNotice, setAutomaticNotice] = useState('')
  const [photoCount, setPhotoCount] = useState(0)
  const photoCountRef = useRef(0)
  const manualRevision = useRef(0)
  const observationEpoch = useRef(0)
  const requestBusy = useRef(false)
  const activeInteraction = useRef<InteractionMode | null>(null)
  const automaticRef = useRef(automatic)
  automaticRef.current = automatic
  const readGuard = useRef(new ObservationSpeechGuard())
  const sequence = useRef(0)
  const currentMode = useRef(mode)
  currentMode.current = mode
  const controller = useRef<AbortController | null>(null)
  const lastQuestion = useRef('')
  const previewUrl = useRef<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const cameraInput = useRef<HTMLInputElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const answer = useRef<HTMLDivElement>(null)
  const speech = useSpeech(language, editQuestion)
  const camera = useCamera(language)
  const busy = ['uploading', 'submitting', 'queued', 'running'].includes(phase)
  const currentResult = result && !stale && !busy ? result : null
  const automaticAvailable = Boolean(session && !healthFailed && health?.worker_connected && photoCount < 20 && !photoLocked)
  const automaticPaused = busy || Boolean(question.trim()) || speech.listening || speech.speaking || result?.status === 'need_confirmation'
  const companion = useAutoCompanion(automatic && mode === 'real_place' && camera.phase === 'live' && automaticAvailable, automaticPaused, observeFrame, () => stopAutomatic(t('Automatic guidance stopped. Please ask directly or try again later.', '자동동행을 멈췄어요. 직접 질문하거나 잠시 후 다시 시작해 주세요.')))

  useEffect(() => {
    let active = true
    api.session().then(value => { if (active && typeof value.session_id === 'string') setSession(value.session_id) })
      .catch(() => { if (active) setHealthFailed(true) })
    api.catalog().then(value => {
      if (!Array.isArray(value.places)) throw new ApiError('INVALID_RESPONSE')
      if (active) { setCatalog(value); setCatalogFailed(false) }
    }).catch(() => { if (active) setCatalogFailed(true) })
    const refresh = () => { api.health().then(value => { if (active) { setHealth(value); setHealthFailed(false); setCheckedAt(new Date().toLocaleTimeString()) } }).catch(() => { if (active) setHealthFailed(true) }) }
    refresh()
    const timer = window.setInterval(refresh, 15000)
    return () => { active = false; clearInterval(timer); controller.current?.abort(); sequence.current += 1; if (previewUrl.current) URL.revokeObjectURL(previewUrl.current) }
  }, [])
  useEffect(() => { document.documentElement.lang = language }, [language])
  useEffect(() => {
    const hide = () => { if (document.visibilityState === 'hidden') { stopAutomatic(t('Automatic companion stopped when you left this page.', '다른 화면으로 이동해 자동동행을 멈췄어요.')); if (activeInteraction.current === 'observe') invalidate() } }
    document.addEventListener('visibilitychange', hide)
    return () => document.removeEventListener('visibilitychange', hide)
  }, [])
  useEffect(() => {
    if (automatic && (camera.phase !== 'live' || !automaticAvailable)) stopAutomatic(t('Automatic companion stopped. Check the camera, connection and photo limit.', '자동동행을 멈췄어요. 카메라·연결·사진 한도를 확인해 주세요.'))
  }, [automatic, camera.phase, automaticAvailable])
  useEffect(() => {
    if (statusOpen && dialog.current && !dialog.current.open) dialog.current.showModal()
    if (!statusOpen && dialog.current?.open) dialog.current.close()
  }, [statusOpen])

  function invalidate() {
    sequence.current += 1
    requestBusy.current = false
    activeInteraction.current = null
    setLocating(false)
    controller.current?.abort()
    speech.stopReading()
    setStale(Boolean(result))
    setPhase('idle')
    setError('')
  }
  function stopAutomatic(notice = '', cancelPending = true) {
    observationEpoch.current += 1
    automaticRef.current = false
    setAutomatic(false)
    companion.interrupt()
    if (cancelPending && activeInteraction.current === 'observe') invalidate()
    if (notice) setAutomaticNotice(notice)
  }
  function prioritizeUser() {
    manualRevision.current += 1
    companion.interrupt()
    if (activeInteraction.current === 'observe') invalidate()
  }
  function editQuestion(text: string) { prioritizeUser(); setQuestion(text) }
  function changeAutomatic(enabled: boolean) {
    if (enabled && !automaticAvailable) return
    automaticRef.current = enabled; setAutomatic(enabled); setAutomaticNotice('')
    if (!enabled) stopAutomatic()
  }
  async function capturePhoto() {
    stopAutomatic(); prioritizeUser()
    const version = manualRevision.current
    const file = await camera.capture()
    if (file && manualRevision.current === version && currentMode.current === 'real_place') choosePhoto(file)
  }
  async function observeFrame(current: () => boolean) {
    if (!current() || photoLockedRef.current || requestBusy.current || question.trim() || speech.listening || document.visibilityState === 'hidden') return
    const version = manualRevision.current
    const file = await camera.capture()
    const valid = () => manualRevision.current === version && !photoLockedRef.current && automaticRef.current && currentMode.current === 'real_place' && camera.isLive() && document.visibilityState !== 'hidden'
    if (!file || !current() || !valid() || requestBusy.current) return
    await submit({ frame: file, interaction: 'observe', valid, question: t('Describe the cultural or historical context of what is visible, and suggest one relevant nearby place from the collection. Ask me to confirm uncertain place or food identity. Do not identify people.', '보이는 풍경의 한국 문화·역사 맥락을 설명하고 수록된 주변 장소 한 곳을 제안해 주세요. 장소나 음식이 불확실하면 먼저 확인하고, 사람을 식별하지 마세요.') })
  }
  async function reconnect() {
    setError('')
    try {
      const [freshSession, freshHealth] = await Promise.all([api.session(), api.health()])
      if (freshSession.session_id !== session) { invalidate(); stopAutomatic(); photoCountRef.current = 0; setPhotoCount(0); setPhoto(previous => previous ? { ...previous, id: null } : null); setResult(null); lastQuestion.current = '' }
      setSession(freshSession.session_id); setHealth(freshHealth); setHealthFailed(false); setCheckedAt(new Date().toLocaleTimeString())
    } catch { setHealthFailed(true); setError(t('Your guide could not connect. Please try again shortly.', '아직 가이드에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.')) }
  }
  function choosePhoto(file?: File) {
    if (!file || currentMode.current !== 'real_place') return
    setPhotoNotice('')
    if (!['image/jpeg', 'image/png'].includes(file.type) || !file.size || file.size > 8 * 1024 * 1024) {
      setPhotoNotice(t('Choose a JPG or PNG photo smaller than 8 MB.', '8MB 이하의 JPG 또는 PNG 사진을 선택해 주세요.')); return
    }
    stopAutomatic(); prioritizeUser(); invalidate(); readGuard.current.reset()
    photoLockedRef.current = true; setPhotoLocked(true)
    identityPlace.current = null
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
    const url = URL.createObjectURL(file)
    previewUrl.current = url
    setPhoto({ file, url, id: null })
  }
  function removePhoto() {
    prioritizeUser(); invalidate(); readGuard.current.reset()
    photoLockedRef.current = false; setPhotoLocked(false)
    identityPlace.current = null
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
    previewUrl.current = null; setPhoto(null); setPhotoNotice('')
  }
  function selectLocation(next: Location, demo = false) {
    prioritizeUser(); setAnchor(null)
    identityPlace.current = null
    setLocation(next); setDemoLocation(demo); setLocationNotice('')
    if (lastQuestion.current && (result || busy)) void submit({ location: next, place: null, shop: null, question: lastQuestion.current })
  }
  function useMyLocation() {
    if (currentMode.current !== 'real_place') return
    const generation = sequence.current
    const current = () => sequence.current === generation && currentMode.current === 'real_place'
    setLocationNotice('')
    if (!navigator.geolocation) { setLocationNotice(t('Location is unavailable. Choose a point on the map.', '위치를 지원하지 않아요. 지도에서 출발점을 골라 주세요.')); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(position => {
      if (!current()) return
      setLocating(false)
      selectLocation({ lat: position.coords.latitude, lng: position.coords.longitude, origin: 'gps' })
    }, () => { if (!current()) return; setLocating(false); setLocationNotice(t('Location permission was unavailable. Tap the map or choose the Seochon demo point.', '위치를 확인하지 못했어요. 지도를 누르거나 서촌 시연 위치를 선택해 주세요.')) }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 })
  }
  function changeRadius(next: Radius) {
    prioritizeUser(); setRadius(next)
    if (lastQuestion.current && (result || busy)) void submit({ radius: next, question: lastQuestion.current })
  }
  function describeError(value: unknown): string {
    if (value instanceof ApiError) {
      if (value.status === 401 || value.status === 403) { setSession(null); setPhoto(previous => previous ? { ...previous, id: null } : null); return t('Your session needs to reconnect. Reconnect, then send your question again.', '다시 연결한 뒤 질문을 보내 주세요.') }
      if (value.code === 'PHOTO_LIMIT') return t('This session has reached its20-photo limit. Automatic companion has stopped. You can continue asking about the current photo.', '이 세션의 사진 20장 한도에 도달해 자동동행을 멈췄어요. 현재 사진에 대한 질문은 계속할 수 있어요.')
      if (value.code === 'JOB_BUSY') return t('Your own question comes first. Automatic companion has stopped while that question finishes.', '직접 보낸 질문이 우선이에요. 답변을 기다리며 자동동행을 멈췄어요.')
      if (value.code === 'TIMEOUT') return t('That took longer than expected. Please try again; your previous answer is not being reused.', '답변이 오래 걸리고 있어요. 다시 질문해 주세요. 이전 답변을 새 답변으로 사용하지 않아요.')
      if (value.code === 'SUPERSEDED') return t('A newer question replaced this one. Please continue with your latest question.', '새 질문으로 바뀌었어요. 가장 최근 질문을 확인해 주세요.')
      if (value.code === 'OFFLINE' || value.status >= 500) return t('Your guide is unavailable right now. Please reconnect or try again.', '지금은 가이드를 이용할 수 없어요. 다시 연결하거나 잠시 후 시도해 주세요.')
      if (value.status === 413) return t('This photo is too large. Please choose one under 8 MB.', '사진이 너무 커요. 8MB 이하로 골라 주세요.')
      if (value.code === 'INVALID_RESPONSE') return t('The answer could not be read safely. Please try again.', '답변을 확인할 수 없어요. 다시 시도해 주세요.')
    }
    return t('The guide could not finish this question. Please try again or check the connection.', '질문을 완료하지 못했어요. 다시 시도하거나 연결 상태를 확인해 주세요.')
  }
  async function submit(options: SubmitOptions = {}) {
    const observing = options.interaction === 'observe'
    const text = (options.question ?? question).trim()
    if (observing && (photoLockedRef.current || requestBusy.current || !options.valid?.() || photoCountRef.current >= 20)) return
    if (!observing) { prioritizeUser(); readGuard.current.reset() }
    if (!text) { setError(t('Ask a question to begin.', '먼저 질문을 입력해 주세요.')); return }
    if (!session) { setError(t('Please reconnect your guide before asking.', '가이드에 다시 연결한 뒤 질문해 주세요.')); return }
    // Typed/voice questions use the view at send time. Confirmation/navigation
    // actions retain the photo they refer to; explicit captures/uploads stay fixed.
    const captureCurrent = !observing && options.question === undefined && mode === 'real_place' && camera.isLive() && !photoLockedRef.current
    const manualVersion = manualRevision.current
    let selectedPhoto = photo
    const newImage = observing || captureCurrent || Boolean(options.frame) || Boolean(selectedPhoto && !selectedPhoto.id)
    if (options.frame) {
      identityPlace.current = null
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
      const url = URL.createObjectURL(options.frame)
      selectedPhoto = { file: options.frame, url, id: null }
      previewUrl.current = url; setPhoto(selectedPhoto)
    }
    if (mode === 'real_place' && !selectedPhoto && !captureCurrent && !result && !anchor && !options.place) { setPhotoNotice(t('Add a photo, capture a view, or choose a cultural starting point first.', '사진을 선택·촬영하거나 문화 장소를 출발점으로 골라 주세요.')); return }
    if (!observing) lastQuestion.current = text
    const generation = ++sequence.current
    const observationVersion = observationEpoch.current
    requestBusy.current = true
    activeInteraction.current = observing ? 'observe' : 'ask'
    setLocating(false)
    controller.current?.abort()
    const nextController = new AbortController()
    controller.current = nextController
    if (!observing) { speech.stopListening(); speech.stopReading() }
    setError(''); setCopyNotice(''); setStale(Boolean(result))
    setPhase(captureCurrent || (selectedPhoto && !selectedPhoto.id && mode === 'real_place') ? 'uploading' : 'submitting')
    const current = () => sequence.current === generation && !nextController.signal.aborted && (!observing || observationEpoch.current === observationVersion)
    try {
      if (captureCurrent) {
        const frame = await camera.capture()
        if (!current()) return
        if (!frame || manualRevision.current !== manualVersion || photoLockedRef.current) { setPhase('idle'); return }
        identityPlace.current = null
        if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
        const url = URL.createObjectURL(frame)
        selectedPhoto = { file: frame, url, id: null }
        previewUrl.current = url; setPhoto(selectedPhoto); setPhotoNotice('')
      }
      let photoId = mode === 'real_place' ? selectedPhoto?.id ?? null : null
      if (selectedPhoto && !photoId && mode === 'real_place') {
        const uploaded = await api.upload(selectedPhoto.file, nextController.signal)
        if (!current()) return
        photoId = uploaded.photo_id
        photoCountRef.current += 1; setPhotoCount(photoCountRef.current)
        const uploadedUrl = selectedPhoto.url
        setPhoto(previous => previous?.url === uploadedUrl ? { ...previous, id: uploaded.photo_id } : previous)
      }
      if (!current()) return
      if (observing && !options.valid?.()) { invalidate(); return }
      const placeId = mode === 'fictional_task' ? null : options.place !== undefined ? options.place : options.shop !== undefined ? options.shop : newImage ? null : identityPlace.current ?? currentResult?.scene.confirmed_place_id ?? currentResult?.scene.confirmed_shop_id ?? null
      const targetKind = catalog?.places.find(place => place.place_id === placeId)?.kind
      const shopId = mode === 'fictional_task' ? null : options.shop !== undefined ? options.shop : targetKind === 'heritage' ? null : placeId && (targetKind === 'restaurant' || currentResult?.scene.confirmed_shop_id === placeId) ? placeId : null
      setPhase('submitting')
      const queued = await api.submit({
        schema_version: 1, session_id: session, question: text, photo_id: photoId,
        dataset_mode: mode, response_language: language, location: mode === 'fictional_task' ? null : options.location ?? location,
        radius_m: options.radius ?? radius,
        confirmed_food_id: options.food !== undefined ? options.food : newImage ? null : currentResult?.scene.confirmed_food_id ?? null,
        confirmed_shop_id: shopId, confirmed_place_id: placeId,
        interaction_mode: observing ? 'observe' : 'ask',
      }, nextController.signal)
      if (!current()) return
      if (typeof queued.request_id !== 'string' || !queued.request_id) throw new ApiError('INVALID_RESPONSE')
      setPhase('queued')
      if (!observing) lastQuestion.current = text
      const received = await waitForResult(queued.request_id, session, nextController.signal, state => { if (current() && (state === 'queued' || state === 'running')) setPhase(state) })
      if (!current()) return
      if (observing && (!options.valid?.() || !camera.isLive())) { stopAutomatic(); return }
      if (received.dataset_mode !== mode || (mode === 'fictional_task' && received.places.length > 0)) throw new ApiError('INVALID_RESPONSE')
      if (received.status === 'failed') throw new ApiError(received.error_code || 'JOB_FAILED')
      // Root only emits proactive questions for cultural landmarks, including
      // recognized landmarks outside the catalog. All other observations stay quiet.
      const observationQuestion = observing ? received.next_question?.trim() : null
      if (observing && !observationQuestion) {
        setAutomaticNotice(t('Looking around quietly. No cultural place to suggest yet.', '풍경을 조용히 살펴보고 있어요. 아직 안내할 문화 장소가 없어요.'))
        setStale(Boolean(result)); setPhase('idle')
        return
      }
      setAutomaticNotice('')
      setResult(received); setStale(false); setPhase(received.status === 'need_confirmation' ? 'need_confirmation' : 'ready')
      if (!observing) setQuestion(previous => previous.trim() === text ? '' : previous)
      if (received.status === 'need_confirmation' || observationQuestion) stopAutomatic(t('Automatic companion stopped so you can confirm what you see.', '보이는 대상을 확인할 수 있도록 자동동행을 멈췄어요.'), false)
      const suggestions = [...(!received.scene.confirmed_food_id ? received.scene.food_candidates.map(item => item.id) : []), ...(!received.scene.confirmed_place_id ? (received.scene.place_candidates ?? []).map(item => item.id) : []), ...received.places.map(place => place.place_id)]
      const spokenText = observing ? received.speech_text.trim() || observationQuestion || '' : received.speech_text
      if (autoReadRef.current && spokenText && (!observing || readGuard.current.shouldRead(spokenText, suggestions))) speech.read(spokenText, received.response_language)
      if (!observing) window.setTimeout(() => { if (current()) answer.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }) }, 100)
    } catch (value) {
      if (!current()) return
      const description = describeError(value)
      if (observing || value instanceof ApiError && value.code === 'PHOTO_LIMIT') stopAutomatic(description)
      setError(description); setPhase('failed')
    } finally {
      if (sequence.current === generation) {
        requestBusy.current = false; activeInteraction.current = null
        if (photoCountRef.current >= 20) stopAutomatic(t('The20-photo session limit has been reached. Automatic companion is off; you can keep asking about the current photo.', '세션 사진 20장 한도에 도달해 자동동행을 껐어요. 현재 사진에 대한 질문은 계속할 수 있어요.'))
      }
    }
  }
  function selectAnchor(place: CatalogPlace, ask = false) {
    prioritizeUser(); readGuard.current.reset()
    identityPlace.current = place.place_id
    const next: Location = { lat: place.lat, lng: place.lng, origin: 'selected' }
    setAnchor(place); setLocation(next); setDemoLocation(false); setLocationNotice('')
    if (ask || result || busy) void submit({ place: place.place_id, shop: place.kind === 'restaurant' ? place.place_id : null, food: null, location: next, question: t('Tell me about the history, culture and visiting etiquette of ', '이 장소의 역사·문화와 방문 예절을 알려 주세요: ') + place.name })
  }
  function confirmPlace(id: string) {
    const place = catalog?.places.find(item => item.place_id === id)
    if (!place) { setLocationNotice(t('This place is not in the available collection. Choose a starting point from the list.', '현재 수록 목록에서 확인할 수 없어요. 목록에서 출발점을 선택해 주세요.')); return }
    selectAnchor(place, true)
  }
  function choosePlace(place: Place) {
    if (place.kind === 'heritage') { selectAnchor(catalog?.places.find(item => item.place_id === place.place_id) ?? { ...place, kind: 'heritage', name_en: place.name }, true); return }
    const selected = catalog?.places.find(item => item.place_id === place.place_id) ?? { ...place, kind: 'restaurant' as const, name_en: place.name }
    const next: Location = { lat: place.lat, lng: place.lng, origin: 'selected' }
    setAnchor(selected); setLocation(next); setDemoLocation(false)
    identityPlace.current = place.place_id
    void submit({ place: place.place_id, shop: place.place_id, location: next, question: t('Tell me about the menu and local culture at ', '이곳의 메뉴와 지역 문화를 알려 주세요: ') + place.name })
  }
  async function copyKorean() {
    try { await navigator.clipboard.writeText(currentResult?.order_ko || ''); setCopyNotice(t('Copied!', '복사했어요!')) }
    catch { setCopyNotice(t('Please select and copy the sentence.', '문장을 선택해 복사해 주세요.')) }
  }
  function changeMode(next: DatasetMode) {
    prioritizeUser(); stopAutomatic(); camera.stop()
    identityPlace.current = null
    currentMode.current = next
    invalidate(); setMode(next); setResult(null); setQuestion(''); lastQuestion.current = ''; setStatusOpen(false)
  }
  function evidenceLink(item: Evidence) {
    const href = safeSourceUrl(item.source)
    return <div className="evidence-item" key={item.id}><span className="evidence-dot" /><div>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{item.source.replace(/^https?:\/\//, '')}<ArrowUpRight size={12} /></a> : <span className="source-text">{item.source}</span>}<small>{item.type === 'example' ? t('Example', '예시') : item.type === 'live_statement' ? t('On-site statement', '현장 발언') : t('Document', '문서')} · {item.as_of || t('Date not provided', '날짜 미상')}</small></div></div>
  }
  const phaseText = phase === 'uploading' ? t('Preparing your photo…', '사진을 준비하고 있어요…') : phase === 'submitting' ? t('Sending your question…', '질문을 보내고 있어요…') : phase === 'queued' ? t('Your guide will be with you shortly…', '가이드가 곧 함께할게요…') : t('Looking at the details and the sources…', '내용과 근거를 살펴보고 있어요…')

  return <div className="app-shell">
    <header className="site-header"><a className="brand" href="#" aria-label="Hangul Donghaeng home"><span className="brand-mark">한</span><span className="brand-word">한글동행<small>HANGUL DONGHAENG</small></span></a><div className="header-actions"><button className="connection-button" aria-label={t('Connection', '연결 상태')} onClick={() => setStatusOpen(true)}><span className={'connection-dot ' + (health && !healthFailed && health.worker_connected ? 'online' : '')} /><span>{healthFailed || !health ? t('Offline', '연결 필요') : health.worker_connected ? t('Guide connected', '가이드 연결됨') : t('Guide connecting', '가이드 준비 중')}</span></button><div className="language-toggle" aria-label={t('Language', '언어')}><button className={language === 'en' ? 'selected' : ''} onClick={() => { speech.stopListening(); speech.stopReading(); setLanguage('en') }} aria-pressed={language === 'en'}>EN</button><button className={language === 'ko' ? 'selected' : ''} onClick={() => { speech.stopListening(); speech.stopReading(); setLanguage('ko') }} aria-pressed={language === 'ko'}>한글</button></div></div></header>
    <main>
      <section className="intro"><div className="intro-copy"><div className="eyebrow"><span />{t('A LITTLE HANGUL. A LITTLE CLOSER.', '한글로, 한 걸음 더 가까이.')}</div><h1>{t('Walk through history.', '역사 속을 걷고,')}<br/><span>{t('Meet a little Korea.', '한국을 조금 더 알아가요.')}</span></h1><p>{t('A palace, a street, a story. Look around, ask what matters, and discover Korean culture — with a meal nearby when you need one.', '궁궐과 골목에 담긴 이야기를 물어보세요. 눈앞의 한국 문화와 역사를 함께 알아가고, 필요하면 주변 식사까지 이어봐요.')}</p></div><div className="intro-stamp" aria-hidden="true"><span className="stamp-sun" /><svg viewBox="0 0 200 120" fill="none"><path d="M20 58 Q55 55 100 20 Q145 55 180 58L169 66H31Z" fill="#e6d7be"/><path d="M35 58Q67 50 100 26Q133 50 165 58" stroke="#716a58" strokeWidth="3"/><path d="M47 66V105M153 66V105M66 66V100M134 66V100M40 105H160M77 75H123V104M100 75V104" stroke="#716a58" strokeWidth="3"/><path d="M16 111H184" stroke="#c9bea8" strokeWidth="2"/></svg><small>함께 걷는 한국 여행</small></div></section>
      {mode === 'fictional_task' && <div className="practice-banner"><BookOpen size={16}/><span>{t('Practice itinerary · fictional places, no real-world map.', '연습 일정 · 가상의 장소이며 실제 지도와 연결하지 않아요.')}</span><button onClick={() => changeMode('real_place')}>{t('Back to explore', '여행으로 돌아가기')}</button></div>}
      {(healthFailed || !session) && <div className="connection-notice" role="status"><WifiOff size={16}/><span>{t('Your guide is not connected yet. Your photo stays on this device until you ask.', '아직 가이드에 연결되지 않았어요. 질문하기 전에는 사진을 보내지 않아요.')}</span><button onClick={() => void reconnect()}><RotateCcw size={13}/>{t('Reconnect', '다시 연결')}</button></div>}
      <div className="workspace">
        <section className="composer panel" aria-labelledby="start-title"><div className="section-top"><span className="step-number">01</span><div><span className="overline">{t('LET’S START HERE', '우리의 여행 시작')}</span><h2 id="start-title">{t('What caught your eye?', '어떤 풍경이 눈에 들어왔나요?')}</h2></div><Sparkles size={20} className="accent-icon"/></div>
          {mode === 'real_place' && <><input ref={fileInput} className="visually-hidden" type="file" accept="image/jpeg,image/png" aria-label={t('Choose a place, food or menu photo', '장소·음식·메뉴 사진 선택')} onChange={e => { choosePhoto(e.target.files?.[0]); e.target.value = '' }}/><input ref={cameraInput} className="visually-hidden" type="file" accept="image/jpeg,image/png" capture="environment" aria-label={t('Take a photo', '사진 촬영')} onChange={e => { choosePhoto(e.target.files?.[0]); e.target.value = '' }}/>
          <CameraPanel camera={camera} language={language} automatic={automatic} automaticAvailable={automaticAvailable} paused={automaticPaused} onAutomatic={changeAutomatic} onCapture={() => void capturePhoto()}/>{photo ? <div className="photo-preview"><img src={photo.url} alt={t('Your selected place, food or menu photo', '선택한 장소·음식·메뉴 사진')}/><span className="photo-label"><Check size={13}/>{t('Your photo', '선택한 사진')}</span><button className="icon-button remove-photo" onClick={removePhoto} aria-label={t('Remove photo', '사진 지우기')}><X size={17}/></button><button className="replace-photo" onClick={() => fileInput.current?.click()}><ImagePlus size={14}/>{t('Change photo', '사진 바꾸기')}</button></div> : <div className="photo-picker"><div className="photo-art" aria-hidden="true"><svg viewBox="0 0 100 85" fill="none"><path d="M30 11Q19 21 31 30M49 5Q37 19 50 27M67 12Q57 22 67 30" stroke="#c58a65" strokeWidth="2.4" strokeLinecap="round"/><ellipse cx="50" cy="40" rx="36" ry="12" fill="#f4e6d4" stroke="#c58a65" strokeWidth="2"/><path d="M14 40Q18 72 50 73Q82 72 86 40" fill="#fffdf8" stroke="#c58a65" strokeWidth="2"/><path d="M25 50Q32 66 50 66" stroke="#ead9c3" strokeWidth="2" strokeLinecap="round"/></svg><span><ImagePlus size={17}/></span></div><h3>{t('A photo is a lovely place to start.', '사진 한 장으로 시작해 볼까요?')}</h3><p>{t('A palace, a street, a dish or a menu.', '궁궐, 골목, 음식, 메뉴판 모두 좋아요.')}</p><div className="photo-actions"><button className="button button-soft" onClick={() => fileInput.current?.click()}><ImagePlus size={16}/>{t('Choose a photo', '사진 선택')}</button><button className="button button-light" onClick={() => cameraInput.current?.click()}><Camera size={16}/>{t('Take one', '촬영')}</button></div><small>JPG · PNG · {t('up to 8 MB', '최대 8MB')}</small></div>}</>}
          {mode === 'real_place' && <div className="input-basis" role="status"><strong>{photoLocked ? t('Saved photo · kept for follow-up questions', '고정 사진 · 후속 질문에도 유지') : camera.phase === 'live' ? t('Current camera view · captured when you ask', '현재 카메라 장면 · 질문을 보낼 때 촬영') : photo ? t('Last photo · camera is off', '마지막 사진 · 카메라 꺼짐') : t('No photo · selected place and conversation only', '사진 없음 · 선택한 장소와 대화만 사용')} </strong>{photoLocked && <button type="button" className="button button-light" onClick={removePhoto}>{t('Use current view', '현재 장면 사용 · 고정 해제')}</button>}<small>{t('Only the latest photo and conversation are used, not a memory of the whole video.', '전체 영상의 기억 없이 마지막 사진과 대화만 사용해요.')}</small></div>}
          {automaticNotice && <p className="inline-notice automatic-notice" role="status"><Info size={14}/>{automaticNotice}</p>}{photoNotice && <p className="inline-notice" role="status"><Info size={14}/>{photoNotice}</p>}
          <form onSubmit={e => { e.preventDefault(); void submit() }}><label className="question-label" htmlFor="question">{t('Ask your little local guide', '동행 가이드에게 물어보세요')}<span>{t('or tap the mic', '마이크로 말해도 돼요')}</span></label><div className={'question-box ' + (speech.listening ? 'is-listening' : '')}><textarea id="question" value={question} onChange={e => editQuestion(e.target.value)} placeholder={mode === 'fictional_task' ? t('Plan a half-day cultural visit using the provided materials.', '제공 자료로 반나절 문화 여행을 계획해 주세요.') : t('What is the story of this place? What should I notice?', '이 장소에는 어떤 이야기가 있나요? 무엇을 살펴보면 좋을까요?')} rows={3} maxLength={4000}/><div className="question-toolbar"><span>{speech.listening ? t('Listening… you can edit the words.', '듣고 있어요… 인식된 말을 수정할 수 있어요.') : t('English & 한국어', '한국어 & English')}</span><button type="button" className={'mic-button ' + (speech.listening ? 'listening' : '')} onClick={() => { prioritizeUser(); speech.startListening() }} aria-label={speech.listening ? t('Stop listening', '음성 입력 멈추기') : t('Ask by voice', '음성으로 질문')} aria-pressed={speech.listening}>{speech.listening ? <Square size={17}/> : <Mic size={19}/>}</button></div></div>
          {!result && <div className="question-suggestions">{(mode === 'fictional_task' ? [[t('A half-day culture trip', '반나절 문화 여행'), t('Plan a half-day cultural trip using the provided visitor needs, dates, and sources.', '방문 조건과 날짜, 근거 자료를 반영해 반나절 문화 여행을 계획해 주세요.')]] : [[t('What is the story here?', '이곳의 이야기는?'), t('Help me understand the history, cultural context and visiting etiquette of what I see.', '눈앞의 장소에 담긴 역사·문화와 방문 예절을 알려 주세요.')] , [t('What should I ask?', '무엇을 확인할까요?'), t('Help me understand this menu. What ingredients should I ask about?', '이 메뉴를 이해하고 싶어요. 어떤 재료를 확인해야 하나요?')]]).map(([label, text]) => <button type="button" key={label} onClick={() => editQuestion(text)}>{label}<ArrowUpRight size={12}/></button>)}</div>}
          <button className="button button-primary ask-button" type="submit" disabled={!session || !question.trim()}>{busy ? <LoaderCircle className="spin" size={18}/> : <Compass size={19}/>}<span>{busy ? t('Ask a new question', '새 질문 보내기') : result ? t('Keep exploring', '이어서 물어보기') : t('Explore with me', '함께 알아보기')}</span><ArrowRight size={18}/></button></form>
          <div className="composer-bottom"><span><ShieldCheck size={13}/>{t('No bookings. No orders. Just a little guidance.', '예약·주문 없이, 필요한 안내만 함께해요.')}</span><label><input type="checkbox" checked={autoRead} onChange={e => setAutoRead(e.target.checked)}/>{t('Read answers aloud', '답변 읽어주기')}</label></div>
          {speech.notice && <p className="inline-notice" role="status"><VolumeX size={14}/>{speech.notice}</p>}
        </section>
        {mode === 'real_place' && <section className="location-panel panel" aria-labelledby="location-title"><div className="section-top"><span className="step-number green">02</span><div><span className="overline">{t('A PLACE TO WANDER', '어디에서 시작할까요')}</span><h2 id="location-title">{t('A little closer to you', '내 주변에서 찾아봐요')}</h2></div><MapPin size={20} className="green-icon"/></div><div className="location-actions"><button className="button button-light" onClick={useMyLocation} disabled={locating}>{locating ? <LoaderCircle size={15} className="spin"/> : <Navigation size={15}/>} {t('Use my location', '내 위치 사용')}</button><button className={'button button-light ' + (demoLocation ? 'active-demo' : '')} onClick={() => selectLocation(SEOCHON, true)}><MapPin size={15}/>{t('Seochon demo', '서촌 시연 위치')}</button></div>
          <div className="anchor-picker"><label htmlFor="place-anchor">{t("Choose a cultural starting point", "문화 장소를 출발점으로 선택")}</label><select id="place-anchor" value={anchor?.place_id ?? ""} onChange={event => { const next = catalog?.places.find(place => place.place_id === event.target.value); if (next) selectAnchor(next) }}><option value="">{t("Choose from our collection", "수록 장소에서 선택해 주세요")}</option>{(["heritage", "restaurant"] as const).map(kind => <optgroup key={kind} label={kind === "heritage" ? t("History & culture", "역사·문화") : t("Nearby meals", "주변 식사")}>{catalog?.places.filter(place => place.kind === kind).map(place => <option value={place.place_id} key={place.place_id}>{language === "en" ? place.name_en + " · " + place.name : place.name}</option>)}</optgroup>)}</select>{catalogFailed && <p role="status">{t("The place collection is not available yet. You can choose a point on the map or use a photo.", "장소 목록을 아직 불러오지 못했어요. 지도에서 지점을 고르거나 사진을 이용해 주세요.")}</p>}{catalog?.places.some(place => place.name.includes("광화문")) && catalog.places.some(place => place.name.includes("경복궁")) && <small>{t("Gwanghwamun is the main gate of Gyeongbokgung, within the same palace complex. These nearby points are not separate palaces.", "광화문은 경복궁의 정문으로 같은 궁궐 단지 안에 있어요. 가까운 두 지점이며 별개의 궁궐이 아니에요.")}</small>}</div><MapView location={location} places={currentResult?.places ?? EMPTY_PLACES} language={language} onLocation={next => selectLocation(next)} onChoosePlace={choosePlace}/>
          <div className="map-caption"><span className={'location-dot ' + (location ? 'chosen' : '')}/>{location ? anchor ? t('Selected starting point · ', '선택한 출발점 · ') + anchor.name : demoLocation ? t('Demo starting point · Seochon, Seoul', '시연 출발점 · 서울 서촌') : location.origin === 'gps' ? t('Starting from your location', '내 위치에서 출발') : t('Starting from your selected point', '선택한 지점에서 출발') : t('Your starting point is not selected yet.', '아직 출발점을 선택하지 않았어요.')}</div>
          <div className="radius-row"><span>{t('Look within', '검색 반경')}</span><div className="radius-control" aria-label={t('Search radius', '검색 반경')}>{([500, 1000, 2000, 3000] as Radius[]).map(value => <button key={value} aria-pressed={radius === value} className={radius === value ? 'selected' : ''} onClick={() => changeRadius(value)}>{value / 1000} km</button>)}</div></div><p className="scope-note">{health ? t('Our curated collection: ' + health.catalog_count + ' place' + (health.catalog_count === 1 ? '' : 's') + '. Distances are straight-line estimates, not walking times.', '수록 장소 ' + health.catalog_count + '곳 기준이에요. 직선거리이며 도보 시간이 아니에요.') : t('Search is limited to our curated collection. Distance is measured in a straight line.', '직접 정리한 수록 장소에서만 찾아요. 거리는 직선거리예요.')}</p>
          {locationNotice && <p className="inline-notice" role="status"><Info size={14}/>{locationNotice}</p>}
        </section>}
      </div>
      <div className="answer-region" ref={answer} aria-live="polite" aria-busy={busy}>
        {busy && <div className="working-panel"><span className="working-icon"><LoaderCircle className="spin" size={23}/></span><div><h3>{phaseText}</h3><p>{t('We’ll keep the sources, the uncertainties, and your question together.', '질문과 근거, 아직 모르는 점을 함께 살펴볼게요.')}</p></div></div>}
        {error && <div className="error-panel" role="alert"><Info size={20}/><div><strong>{t('Let’s try that again.', '다시 한번 해볼까요?')}</strong><p>{error}</p><button onClick={() => session ? void submit({ question: lastQuestion.current || question }) : void reconnect()}><RotateCcw size={14}/>{session ? t('Try again', '다시 시도') : t('Reconnect', '다시 연결')}</button></div></div>}
        {result && <section className={'result-panel ' + (stale || busy ? 'is-stale' : '')} aria-label={t('Your guide’s answer', '가이드 답변')}><div className="answer-heading"><span className="answer-symbol"><Sparkles size={21}/></span><div><span className="overline">{t('YOUR LITTLE DISCOVERY', '함께 찾은 작은 발견')}</span><h2>{result.status === 'need_confirmation' ? t('One little question first.', '먼저 한 가지만 확인할게요.') : t('Here’s a thoughtful place to start.', '이렇게 시작해 보면 어떨까요?')}</h2></div><button className="icon-button read-answer" disabled={!currentResult} onClick={() => speech.speaking ? speech.stopReading() : speech.read(result.speech_text, result.response_language)} aria-label={speech.speaking ? t('Stop reading', '읽기 멈추기') : t('Read answer aloud', '답변 읽어주기')}>{speech.speaking ? <VolumeX size={20}/> : <Volume2 size={20}/>}</button></div>
          {(stale || busy) && <div className="stale-label">{t('Previous answer · waiting for an update. These recommendations are inactive.', '이전 답변 · 새 답변을 기다리고 있어요. 추천은 비활성 상태예요.')}</div>}
          <p className="answer-text">{result.speech_text}</p>
          <div className="answer-meta"><Check size={13}/>{t('Last answer', '마지막 답변')} · {Number.isFinite(Date.parse(result.captured_at)) ? new Date(result.captured_at).toLocaleString(language === 'ko' ? 'ko-KR' : 'en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : t('Time unavailable', '시각 미상')}</div>
          {result.scene.food_candidates.length > 0 && !result.scene.confirmed_food_id && <div className="confirmation-box"><strong>{t('Which one looks right?', '어떤 음식인가요?')}</strong><div>{result.scene.food_candidates.map(food => <button key={food.id} disabled={!currentResult} onClick={() => void submit({ food: food.id, question: t('Yes, I mean ', '이 음식이 맞아요: ') + food.name_ko })}><span>{food.name_ko}</span><small>{food.name_en}</small><ArrowRight size={15}/></button>)}</div></div>}
          {(result.scene.place_candidates ?? []).length > 0 && !result.scene.confirmed_place_id && <div className="confirmation-box place-confirmation"><strong>{t("Could this be the place? Please confirm.", "이 장소가 맞나요? 먼저 확인해 주세요.")}</strong><div>{result.scene.place_candidates?.map(place => <button key={place.id} disabled={!currentResult || !catalog?.places.some(item => item.place_id === place.id)} onClick={() => confirmPlace(place.id)}><span>{place.name_ko}</span><small>{place.name_en}</small><ArrowRight size={15}/></button>)}</div><small>{t("A photo alone does not establish the location. Confirming chooses the collection’s map point.", "사진만으로 위치를 확정하지 않아요. 확인하면 수록된 지도 지점을 출발점으로 선택해요.")}</small></div>}{result.places.length > 0 && <div className="place-list">{result.places.map((place, index) => <button className="place-card" key={place.place_id} disabled={!currentResult} onClick={() => choosePlace(place)}><span className="place-number">{index + 1}</span><div><span className="place-kind">{place.kind === "heritage" ? t("History & culture", "역사·문화") : t("Restaurant", "음식점")}</span><strong>{place.name}</strong><small><MapPin size={12}/>{Math.round(place.distance_m)} m · {t('straight-line distance', '직선거리')}</small></div><ArrowUpRight size={20}/></button>)}</div>}
          {mode === "real_place" && (result.scene.confirmed_place_id || result.scene.confirmed_shop_id) && <div className="discovery-actions"><button className="button button-soft" disabled={!currentResult} onClick={() => void submit({ food: null, question: t("Find a restaurant near my selected starting point. Keep the cultural place as the starting point, not as a restaurant.", "선택한 출발점 주변의 음식점을 찾아 주세요. 문화 장소를 식당으로 바꾸지 말고 출발점으로 유지해 주세요.") })}><Utensils size={15}/>{t("Find a meal nearby", "주변 식사로 이어보기")}</button><button className="button button-light" disabled={!currentResult} onClick={() => void submit({ food: null, question: t("Find a cultural or historical place near my selected starting point. Explain its context and what is uncertain.", "선택한 출발점 주변의 역사·문화 장소를 찾아 맥락과 미확인을 알려 주세요.") })}><BookOpen size={15}/>{t("Explore nearby history", "주변 역사로 이어보기")}</button></div>}{result.menus.length > 0 && <div className="menus-grid">{result.menus.map((menu, index) => <article className="menu-card" key={menu.name_ko + index}><span className="menu-icon"><Utensils size={19}/></span><span className="menu-index">0{index + 1}</span><h3>{menu.name_ko}</h3><p>{menu.description}</p><div className="menu-source-ids">{menu.evidence_ids.join(' · ')}</div>{menu.unknowns.length > 0 && <div className="menu-unknowns"><Info size={14}/><span>{menu.unknowns.join(' · ')}</span></div>}</article>)}</div>}
          {result.claims.filter(claim => claim.scope === 'culture').length > 0 && <div className="culture-card"><BookOpen size={21}/><div><span className="overline">{t('A LITTLE CULTURE', '한 걸음 더, 문화 이야기')}</span>{result.claims.filter(claim => claim.scope === 'culture').map((claim, index) => <p key={index}>{claim.text}<small>{claim.evidence_ids.join(' · ')}</small></p>)}</div></div>}
          {result.itinerary.length > 0 && <div className="itinerary"><h3>{t('Your practice itinerary', '연습 여행 일정')}</h3><p className="scope-note">{t('Fictional places from the practice materials.', '연습 자료의 가상 장소예요.')}</p>{result.itinerary.map((item, index) => <div className="itinerary-stop" key={index}><time>{item.time}</time><div>{item.activity}<small>{item.buffer_minutes === null ? t('Travel buffer not confirmed', '이동 여유 미확인') : t('Buffer: ', '여유: ') + item.buffer_minutes + t(' minutes', '분')} · {item.evidence_ids.join(' · ')}</small></div></div>)}</div>}
          {(result.unknowns.length > 0 || result.next_question) && <div className="unknown-box"><Info size={19}/><div><h3>{t('A little more to check', '조금 더 확인할 점')}</h3>{result.unknowns.map((unknown, index) => <p key={index}>{unknown}</p>)}{result.next_question && <p className="next-question">{result.next_question}</p>}</div></div>}
          {result.order_ko && <div className="korean-card"><div><span className="overline">{t('A LITTLE HANGUL TO TAKE WITH YOU', '함께 가져갈 한글 한 문장')}</span><p lang="ko">{result.order_ko}</p><small>{t('A phrase for you to say. Nothing is sent or ordered.', '직접 말할 수 있는 초안이에요. 주문이나 발송은 하지 않아요.')}</small></div><div><button className="icon-button" disabled={!currentResult} onClick={() => void copyKorean()} aria-label={t('Copy Korean sentence', '한글 문장 복사')}><Copy size={18}/></button><button className="icon-button" disabled={!currentResult} onClick={() => speech.read(result.order_ko!, 'ko')} aria-label={t('Read Korean sentence', '한글 문장 읽기')}><Volume2 size={18}/></button></div>{copyNotice && <span className="copy-notice" role="status">{copyNotice}</span>}</div>}
          <details className="sources"><summary><span><BookOpen size={15}/>{t('Sources & what we considered', '출처와 판단 이유')}<small>{result.evidence.length}</small></span><ChevronDown size={16}/></summary><div className="source-content">{result.evidence.map(evidenceLink)}{result.conflicts.map((conflict, index) => <div className="conflict" key={index}><strong>{conflict.decision}</strong><p>{conflict.reason}</p><small>{conflict.evidence_ids.join(' · ')}</small></div>)}{result.evidence.length === 0 && <p>{t('No source was provided for this answer.', '이 답변에는 출처가 제공되지 않았어요.')}</p>}</div></details>
          {currentResult && <div className="download-row"><span><Globe2 size={15}/>{t('Take your travel card with you.', '여행 카드를 가져가세요.')}</span><div>{(['html', 'json', ...(mode === 'fictional_task' ? ['md'] : [])] as string[]).map(format => <a className="download-link" key={format} href={'/api/results/' + encodeURIComponent(result.request_id) + '/download?format=' + format} download><Download size={14}/>{format.toUpperCase()}</a>)}</div></div>}
        </section>}
        {!result && !busy && !error && <section className="empty-guide"><span><Compass size={25}/></span><div><h3>{t('The best discoveries start with a question.', '좋은 여행은 작은 질문에서 시작돼요.')}</h3><p>{t('Your places, local stories, and useful Korean phrases will appear here.', '찾은 장소와 문화 이야기, 필요한 한글 문장을 여기에 모아 드릴게요.')}</p></div></section>}
      </div>
    </main>
    <footer><span className="footer-brand">한글로 더 가까이.</span><p>{t('A Hangul Day companion for curious travelers.', '한글날, 한국을 알아가는 여행의 동행.')}</p><button onClick={() => setStatusOpen(true)}>{t('Connection & privacy', '연결 상태와 개인정보')}<ArrowUpRight size={12}/></button></footer>
    <dialog ref={dialog} className="status-dialog" onClose={() => setStatusOpen(false)} onClick={e => { if (e.target === e.currentTarget) setStatusOpen(false) }}><div className="dialog-heading"><h2>{t('Connection & demo status', '연결 및 시연 상태')}</h2><button className="icon-button" onClick={() => setStatusOpen(false)} aria-label={t('Close status', '상태 닫기')}><X size={19}/></button></div><p>{t('These details describe the latest server report, not a completed runtime or safety test. A self-hosted guide can be connected without a hosted API configuration report. Configuration and sandbox reports are separate from worker connectivity.', '아래는 서버의 최신 보고이며 실제 실행·안전 검증의 통과를 뜻하지 않아요. 자체 호스팅 가이드는 호스팅 API 설정 보고 없이도 연결될 수 있어요. 설정·샌드박스 보고와 worker 연결은 별개예요.')}</p><dl className="health-list">{[[t('Service reachable', '서비스 연결'), Boolean(health && !healthFailed)], [t('Browser session', '브라우저 세션'), Boolean(session)], [t('Worker connected', 'worker 연결'), Boolean(!healthFailed && health?.worker_connected)], [t('Hosted API configuration', '호스팅 API 설정'), Boolean(!healthFailed && health?.model_configured)], [t('Sandbox verified by server', '서버 보고상 샌드박스 검증'), Boolean(!healthFailed && health?.sandbox_verified)]].map(([label, ok]) => <div key={String(label)}><dt>{label}</dt><dd className={ok ? 'health-ok' : 'health-wait'}>{ok ? <Check size={13}/> : <Info size={13}/>} {ok ? t('Reported', '보고됨') : t('Not confirmed', '미확인')}</dd></div>)}</dl><small>{t('Last checked', '마지막 확인')}: {checkedAt || t('Not yet', '아직 없음')}</small><button className="button button-soft dialog-reconnect" onClick={() => void reconnect()}><RotateCcw size={15}/>{t('Refresh connection', '연결 새로고침')}</button><div className="privacy-note"><ShieldCheck size={18}/><p>{t('When you send a question or enable automatic companion, sampled photos are sent for analysis; the camera preview stays on this device. Voice input may use your browser’s external speech service. Map tiles are requested from OpenStreetMap. Location is used after you choose or allow it.', '질문을 보내거나 자동동행을 켜면 샘플 사진을 분석을 위해 전송해요. 카메라 미리보기는 내 기기에만 남아요. 음성 인식은 브라우저의 외부 서비스를 사용할 수 있고, 지도는 OpenStreetMap 타일을 받아요. 위치는 직접 선택하거나 허용할 때 사용해요.')}</p></div><button className="practice-link" onClick={() => changeMode(mode === 'real_place' ? 'fictional_task' : 'real_place')}><BookOpen size={15}/>{mode === 'real_place' ? t('Try the fictional practice itinerary', '가상 자료로 연습 일정 만들기') : t('Return to real-place exploration', '실제 장소 여행으로 돌아가기')}<ArrowRight size={14}/></button></dialog>
  </div>
}
