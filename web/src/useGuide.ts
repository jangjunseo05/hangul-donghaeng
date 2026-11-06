import { useEffect, useRef, useState } from 'react'
import { api, ApiError, safeSourceUrl, waitForResult } from './api'
import { useSpeech } from './useSpeech'
import { useCamera } from './useCamera'
import { useAutoCompanion } from './useAutoCompanion'
import { useSceneGate } from './useSceneGate'
import { ObservationSpeechGuard } from './autoCompanion'
import { blockedCount } from './trace'
import type { ObserveOutcome } from './autoCompanion'
import type { JobStage } from './contract'
import type { Catalog, CatalogPlace, DatasetMode, GuideResult, Health, InteractionMode, Language, Location, Place, Radius, TraceEvent } from './types'

export type Phase = 'idle' | 'uploading' | 'submitting' | 'queued' | 'running' | 'ready' | 'need_confirmation' | 'failed'
export type SubmitOptions = { question?: string; food?: string | null; shop?: string | null; place?: string | null; radius?: Radius; location?: Location; frame?: File; interaction?: InteractionMode; valid?: () => boolean }
export const AWAIT_ANSWER_MS = 60000
const TRANSIENT = new Set(['TIMEOUT', 'OFFLINE', 'JOB_FAILED', 'SERVER_ERROR', 'INVALID_RESPONSE'])
const isTransient = (value: unknown) => value instanceof ApiError && value.status !== 401 && value.status !== 403 && (TRANSIENT.has(value.code) || value.status >= 500)

/** All guide state and actions (moved unchanged from the former single-page App). */
export function useGuide() {
  const [language, setLanguage] = useState<Language>('en')
  const t = (en: string, ko: string) => language === 'ko' ? ko : en
  const [session, setSession] = useState<string | null>(null)
  const sessionRef = useRef(session)
  sessionRef.current = session
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
  const [mapPickerOpen, setMapPickerOpen] = useState(false)
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
  // Decision 2: a proposal pauses automatic mode; with no answer for 60 s it resumes on its own.
  const [awaitingAnswer, setAwaitingAnswer] = useState(false)
  const awaitingTimer = useRef<number | null>(null)
  const [stage, setStage] = useState<JobStage | null>(null)
  // Broker trace (contract "Agent trace"): live while busy; kept with the shown result. startedAt is the client clock at send.
  const [trace, setTrace] = useState<{ events: TraceEvent[]; startedAt: number }>({ events: [], startedAt: 0 })
  const [resultTrace, setResultTrace] = useState<{ events: TraceEvent[]; totalMs: number } | null>(null)
  // Tool calls and checks the broker rejected in this browser session (summed from each request's trace).
  const [sessionBlocked, setSessionBlocked] = useState(0)
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
  const automaticPaused = busy || Boolean(question.trim()) || speech.listening || speech.speaking || awaitingAnswer
  const automaticActive = automatic && mode === 'real_place' && camera.phase === 'live' && automaticAvailable
  const companion = useAutoCompanion(automaticActive, automaticPaused, observeFrame, () => stopAutomatic(t('Automatic guidance stopped. Please ask directly or try again later.', '자동동행을 멈췄어요. 직접 질문하거나 잠시 후 다시 시작해 주세요.')))
  const sceneGate = useSceneGate(camera.videoRef, automaticActive, !automaticPaused, () => companion.notifySceneChange())

  useEffect(() => {
    let active = true
    api.session().then(value => { if (active && typeof value.session_id === 'string') setSession(value.session_id) })
      .catch(() => { if (active) setHealthFailed(true) })
    api.catalog().then(value => {
      if (!Array.isArray(value.places)) throw new ApiError('INVALID_RESPONSE')
      if (active) { setCatalog(value); setCatalogFailed(false) }
    }).catch(() => { if (active) setCatalogFailed(true) })
    // A failed first session request is retried while the service is reachable (tabs wait for the cookie).
    const ensureSession = () => { if (!sessionRef.current) api.session().then(value => { if (active && typeof value.session_id === 'string') setSession(value.session_id) }).catch(() => {}) }
    const refresh = (retrySession = true) => { api.health().then(value => { if (active) { setHealth(value); setHealthFailed(false); setCheckedAt(new Date().toLocaleTimeString()); if (retrySession) ensureSession() } }).catch(() => { if (active) setHealthFailed(true) }) }
    refresh(false)
    const timer = window.setInterval(refresh, 15000)
    const sessionRetry = window.setTimeout(ensureSession, 3000)
    return () => { active = false; clearInterval(timer); clearTimeout(sessionRetry); controller.current?.abort(); sequence.current += 1; if (previewUrl.current) URL.revokeObjectURL(previewUrl.current) }
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
    clearAwaiting()
    observationEpoch.current += 1
    automaticRef.current = false
    setAutomatic(false)
    companion.interrupt()
    if (cancelPending && activeInteraction.current === 'observe') invalidate()
    if (notice) setAutomaticNotice(notice)
  }
  function clearAwaiting() {
    if (awaitingTimer.current !== null) clearTimeout(awaitingTimer.current)
    awaitingTimer.current = null
    setAwaitingAnswer(false)
  }
  function awaitAnswer() {
    clearAwaiting()
    setAwaitingAnswer(true)
    setAutomaticNotice(t('Paused so you can answer. I will keep looking in 60 seconds if you do not.', '답할 수 있도록 잠시 멈췄어요. 60초 동안 답이 없으면 다시 살펴볼게요.'))
    awaitingTimer.current = window.setTimeout(() => {
      awaitingTimer.current = null
      setAwaitingAnswer(false)
      if (automaticRef.current) setAutomaticNotice(t('Looking around again.', '다시 둘러보고 있어요.'))
    }, AWAIT_ANSWER_MS)
  }
  function prioritizeUser() {
    clearAwaiting()
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
  async function observeFrame(current: () => boolean): Promise<ObserveOutcome | void> {
    if (!current() || photoLockedRef.current || requestBusy.current || question.trim() || speech.listening || document.visibilityState === 'hidden') return
    // Scene gate: only a changed, steady, sharp view is worth a request.
    if (!sceneGate.ready()) return 'skipped'
    const version = manualRevision.current
    const file = await camera.capture()
    const valid = () => manualRevision.current === version && !photoLockedRef.current && automaticRef.current && currentMode.current === 'real_place' && camera.isLive() && document.visibilityState !== 'hidden'
    if (!file || !current() || !valid() || requestBusy.current) return
    const frame = sceneGate.current()
    const outcome = await submit({ frame: file, interaction: 'observe', valid, question: t('Describe the cultural or historical context of what is visible, and suggest one relevant nearby place from the collection. Ask me to confirm uncertain place or food identity. Do not identify people.', '보이는 풍경의 한국 문화·역사 맥락을 설명하고 수록된 주변 장소 한 곳을 제안해 주세요. 장소나 음식이 불확실하면 먼저 확인하고, 사람을 식별하지 마세요.') })
    // A failed send does not count: the same view may be tried again.
    if (outcome === 'shown' || outcome === 'quiet') sceneGate.markSent(frame)
    return outcome
  }
  async function reconnect() {
    setError('')
    try {
      const [freshSession, freshHealth] = await Promise.all([api.session(), api.health()])
      if (freshSession.session_id !== session) { invalidate(); stopAutomatic(); photoCountRef.current = 0; setPhotoCount(0); setPhoto(previous => previous ? { ...previous, id: null } : null); setResult(null); setResultTrace(null); setSessionBlocked(0); lastQuestion.current = '' }
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
  function selectLocation(next: Location) {
    prioritizeUser(); setAnchor(null)
    identityPlace.current = null
    setLocation(next); setLocationNotice('')
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
    }, () => { if (!current()) return; setLocating(false); setLocationNotice(t('Location permission was unavailable. Use Choose on map to select a point.', '위치를 확인하지 못했어요. 지도에서 선택 버튼으로 지점을 직접 골라 주세요.')) }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 })
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
  async function submit(options: SubmitOptions = {}): Promise<ObserveOutcome | void> {
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
    const startedAt = Date.now()
    let latestTrace: TraceEvent[] = []
    setTrace({ events: [], startedAt })
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
        const uploaded = await api.upload(selectedPhoto.file, nextController.signal, observing ? 'observe' : 'capture')
        if (!current()) return
        photoId = uploaded.photo_id
        // Observe frames do not count toward the 20-photo bound (contract M2).
        if (!observing) { photoCountRef.current += 1; setPhotoCount(photoCountRef.current) }
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
      const received = await waitForResult(queued.request_id, session, nextController.signal, (state, nextStage, events) => { if (!current()) return; latestTrace = events; setTrace({ events, startedAt }); if (state === 'queued' || state === 'running') { setPhase(state); setStage(nextStage ?? null) } })
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
        return 'quiet'
      }
      setAutomaticNotice('')
      setResult(received); setResultTrace({ events: latestTrace, totalMs: Date.now() - startedAt }); setStale(false); setPhase(received.status === 'need_confirmation' ? 'need_confirmation' : 'ready')
      if (!observing) setQuestion(previous => previous.trim() === text ? '' : previous)
      const suggestions = [...(!received.scene.confirmed_food_id ? received.scene.food_candidates.map(item => item.id) : []), ...(!received.scene.confirmed_place_id ? (received.scene.place_candidates ?? []).map(item => item.id) : []), ...received.places.map(place => place.place_id), ...(received.scene.observed_place_name?.trim() ? ['name:' + received.scene.observed_place_name.trim().toLowerCase()] : [])]
      const spokenText = observing ? received.speech_text.trim() || observationQuestion || '' : received.speech_text
      // The same place is not spoken (or paused for) twice in an automatic session.
      const fresh = !observing || readGuard.current.shouldRead(spokenText, suggestions)
      const proposal = received.status === 'need_confirmation' || Boolean(observationQuestion)
      if (proposal && automaticRef.current && fresh) awaitAnswer()
      if (autoReadRef.current && spokenText && fresh) speech.read(spokenText, received.response_language)
      if (!observing) window.setTimeout(() => { if (current()) answer.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }) }, 100)
      return 'shown'
    } catch (value) {
      if (!current()) return
      const description = describeError(value)
      // Transient observation failures back off (scheduler stops after 3 in a row); the rest stop at once.
      if (observing && isTransient(value)) { setAutomaticNotice(t('Having trouble reaching the guide. Trying again a little later.', '가이드 연결이 불안정해요. 조금 뒤에 다시 살펴볼게요.')); setPhase('idle'); return 'error' }
      if (observing || value instanceof ApiError && value.code === 'PHOTO_LIMIT') stopAutomatic(description)
      setError(description); setPhase('failed')
    } finally {
      const blocked = blockedCount(latestTrace)
      if (blocked) setSessionBlocked(count => count + blocked)
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
    setAnchor(place); setLocation(next); setLocationNotice('')
    if (ask || result || busy) void submit({ place: place.place_id, shop: place.kind === 'restaurant' ? place.place_id : null, food: null, location: next, question: t('Tell me about the history, culture and visiting etiquette of ', '이 장소의 역사·문화와 방문 예절을 알려 주세요: ') + place.name })
  }
  function confirmPlace(id: string) {
    // OSM candidates (contract M2): only ids the broker issued to this session; the server owns their coordinates.
    if (id.startsWith('osm:')) {
      prioritizeUser(); readGuard.current.reset(); identityPlace.current = id
      const candidate = result?.scene.place_candidates?.find(item => item.id === id)
      void submit({ place: id, shop: null, food: null, question: t('Tell me about the history, culture and visiting etiquette of ', '이 장소의 역사·문화와 방문 예절을 알려 주세요: ') + (candidate ? t(candidate.name_en, candidate.name_ko) : id) })
      return
    }
    const place = catalog?.places.find(item => item.place_id === id)
    if (!place) { setLocationNotice(t('This place is not in the available collection. Choose a starting point from the list.', '현재 수록 목록에서 확인할 수 없어요. 목록에서 출발점을 선택해 주세요.')); return }
    selectAnchor(place, true)
  }
  function choosePlace(place: Place) {
    const selected = catalog?.places.find(item => item.place_id === place.place_id)
    if (!selected || place.place_id.startsWith('osm:')) {
      const source = currentResult?.evidence.find(item => item.id === place.source_id)?.source
      const safeUrl = source ? safeSourceUrl(source) : undefined
      const osmUrl = safeUrl && ['www.openstreetmap.org', 'openstreetmap.org'].includes(new URL(safeUrl).hostname) ? safeUrl : undefined
      if (!osmUrl && (!Number.isFinite(place.lat) || !Number.isFinite(place.lng) || Math.abs(place.lat) > 90 || Math.abs(place.lng) > 180)) return
      window.open(osmUrl ?? `https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lng}#map=18/${place.lat}/${place.lng}`, '_blank', 'noopener,noreferrer')
      return
    }
    if (selected.kind === 'heritage') { selectAnchor(selected, true); return }
    const next: Location = { lat: place.lat, lng: place.lng, origin: 'selected' }
    setAnchor(selected); setLocation(next)
    identityPlace.current = place.place_id
    void submit({ place: place.place_id, shop: place.place_id, location: next, question: t('Tell me about the menu and local culture at ', '이곳의 메뉴와 지역 문화를 알려 주세요: ') + place.name })
  }
  /** "Not this": drop the suggestion and look again. */
  function dismissResult() {
    prioritizeUser(); invalidate(); readGuard.current.reset()
    identityPlace.current = null
    setResult(null); setResultTrace(null); setStale(false)
  }
  async function copyKorean() {
    try { await navigator.clipboard.writeText(currentResult?.order_ko || ''); setCopyNotice(t('Copied!', '복사했어요!')) }
    catch { setCopyNotice(t('Please select and copy the sentence.', '문장을 선택해 복사해 주세요.')) }
  }
  function changeMode(next: DatasetMode) {
    prioritizeUser(); stopAutomatic(); camera.stop()
    identityPlace.current = null
    currentMode.current = next
    invalidate(); setMode(next); setResult(null); setResultTrace(null); setQuestion(''); lastQuestion.current = ''; setStatusOpen(false)
  }
  const stageText = phase !== 'running' || !stage ? null : stage === 'observing' ? t('Looking at your photo…', '사진을 살펴보고 있어요…') : stage === 'matching' ? t('Matching it with nearby places…', '주변 장소와 맞춰 보고 있어요…') : t('Writing your story…', '이야기를 쓰고 있어요…')
  const phaseText = stageText ?? (phase === 'uploading' ? t('Preparing your photo…', '사진을 준비하고 있어요…') : phase === 'submitting' ? t('Sending your question…', '질문을 보내고 있어요…') : phase === 'queued' ? t('Your guide will be with you shortly…', '가이드가 곧 함께할게요…') : t('Looking at the details and the sources…', '내용과 근거를 살펴보고 있어요…'))

  return {
    t, language, setLanguage, session, health, healthFailed, checkedAt, statusOpen, setStatusOpen, mode, question, photo, photoLocked, photoNotice,
    location, mapPickerOpen, setMapPickerOpen, radius, locating, locationNotice, result, stale, phase, error, copyNotice, autoRead, setAutoRead,
    catalog, catalogFailed, anchor, automatic, automaticNotice, busy, currentResult, automaticAvailable, automaticPaused, speech, camera,
    fileInput, cameraInput, dialog, answer, lastQuestion, phaseText, stage, awaitingAnswer, trace, resultTrace, sessionBlocked,
    editQuestion, changeAutomatic, capturePhoto, reconnect, choosePhoto, removePhoto, selectLocation, useMyLocation, changeRadius, submit,
    selectAnchor, confirmPlace, choosePlace, copyKorean, changeMode, dismissResult, stopAutomatic, prioritizeUser,
  }
}
export type Guide = ReturnType<typeof useGuide>
