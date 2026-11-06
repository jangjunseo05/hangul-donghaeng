import { useEffect, useMemo, useState } from 'react'
import { Camera, Check, ChevronUp, ExternalLink, ImagePlus, Info, LoaderCircle, RefreshCw, ShieldCheck, X } from 'lucide-react'
import type { Guide } from '../useGuide'
import { chromeIntentUrl, detectInAppBrowser } from '../inApp'
import Composer from '../components/Composer'
import ResultDetails from '../components/ResultDetails'
import { BottomSheet } from '../components/shell'
import { InfoTip } from '../components/cards'
import { formatSeconds, totalMs } from '../trace'
import { ConnectionNotices } from '../components/StatusDialog'

function InAppNotice({ g }: { g: Guide }) {
  const { t } = g
  const browser = useMemo(() => detectInAppBrowser(navigator.userAgent), [])
  const [copied, setCopied] = useState(false)
  if (!browser) return null
  return <div className="in-app-notice" role="status"><Info size={15}/><div>
    <strong>{t(`Open in ${browser.platform === 'ios' ? 'Safari' : 'Chrome'} for the camera`, `카메라는 ${browser.platform === 'ios' ? 'Safari' : 'Chrome'}에서 열어 주세요`)}</strong>
    <p>{t(`${browser.name}'s built-in browser may block the camera and voice.`, `${browser.name} 앱 안의 브라우저는 카메라·음성을 막을 수 있어요.`)}</p>
    <div className="in-app-actions">
      {browser.platform === 'android' && <a className="button button-soft" href={chromeIntentUrl(location.href)}><ExternalLink size={14}/>{t('Open in Chrome', 'Chrome으로 열기')}</a>}
      <button type="button" className="button button-light" onClick={() => { void navigator.clipboard?.writeText(location.href).then(() => setCopied(true), () => {}) }}>{copied ? t('Link copied', '링크 복사됨') : t('Copy link', '링크 복사')}</button>
    </div>
    {browser.platform === 'ios' && <small>{t('Tap ••• or the share icon, then “Open in Safari”.', '••• 또는 공유 버튼을 누르고 “Safari로 열기”를 선택하세요.')}</small>}
  </div></div>
}

const firstSentence = (text: string) => text.trim().split(/(?<=[.!?。])\s+/)[0] ?? ''

/**
 * U4 live caption: in automatic companion mode the latest observation is one line over the viewfinder
 * (webcam-VLM style). Tapping it opens the full answer sheet.
 */
function LiveCaption({ g, onOpen, aboveSheet }: { g: Guide; onOpen(): void; aboveSheet: boolean }) {
  const { t, busy, requestKind, phaseText, result, resultOrigin, resultTrace, automaticNotice, stale } = g
  const watching = busy && requestKind === 'observe'
  const shown = result && resultOrigin === 'observe' && !stale ? result : null
  const name = shown?.scene.observed_place_name?.trim()
  const line = shown ? (name ? name + ' — ' : '') + firstSentence(shown.speech_text) : watching ? phaseText : automaticNotice
  if (!line) return null
  const ms = shown && resultTrace ? totalMs(resultTrace.events) : 0
  return <button type="button" className={'live-caption' + (watching ? ' is-working' : '') + (aboveSheet ? ' above-sheet' : '')} onClick={onOpen} disabled={!shown} aria-label={shown ? t('Live caption: ', '실시간 자막: ') + line + t('. Open details', '. 자세히 보기') : undefined}>
    <span className="live-dot" aria-hidden="true">{watching ? <LoaderCircle className="spin" size={13}/> : <i/>}</span>
    <span className="live-text" aria-live={shown ? 'polite' : 'off'}>{line}</span>
    {ms > 0 && <span className="live-ms">{formatSeconds(ms)}</span>}
    {shown && <ChevronUp size={16} aria-hidden="true"/>}
  </button>
}

/** Camera-first screen: full viewfinder, answer sheet over it, question dock below. */
export default function LookScreen({ g, hidden }: { g: Guide; hidden: boolean }) {
  const { t, mode, camera, photo, photoLocked, fileInput, cameraInput, choosePhoto, removePhoto, automatic, automaticAvailable, automaticPaused, changeAutomatic, capturePhoto, busy, error, result } = g
  const live = camera.phase === 'live'
  const showPhoto = Boolean(photo && (photoLocked || !live))
  const real = mode === 'real_place'
  const sheet = Boolean(busy || error || result)
  // Automatic mode: while the guide is watching, the sheet stays down and the caption shows progress.
  // A new answer (a proposal or an ask) opens the sheet; collapsing it leaves the answer as a one-line caption.
  const captionMode = real && live && !showPhoto && g.automatic
  const watching = captionMode && busy && g.requestKind === 'observe'
  const [sheetOpen, setSheetOpen] = useState(true)
  useEffect(() => { setSheetOpen(true) }, [result, error])
  useEffect(() => { if (watching && g.resultOrigin !== 'ask') setSheetOpen(false) }, [watching, g.resultOrigin])
  // Photo label/change/remove: over the photo, or in the top row while an answer sheet is up.
  const photoActions = <><span className="photo-label"><Check size={13}/>{t('Your photo', '선택한 사진')}</span><button className="icon-button remove-photo" onClick={removePhoto} aria-label={t('Remove photo', '사진 지우기')}><X size={17}/></button><button className="replace-photo" onClick={() => fileInput.current?.click()}><ImagePlus size={14}/>{t('Change photo', '사진 바꾸기')}</button></>
  const controls = real && <div className={'stage-controls' + (sheet ? ' compact' : '')}>
        {live ? <>
          <button type="button" className="round-button" onClick={() => fileInput.current?.click()} aria-label={t('Choose a photo', '사진 선택')}><ImagePlus size={21}/></button>
          <button type="button" className="shutter" onClick={() => void capturePhoto()} aria-label={t('Capture a photo', '사진 고정 촬영')}><span/></button>
          {camera.canSwitch ? <button type="button" className="round-button" onClick={() => void camera.switchCamera()} aria-label={t('Switch camera', '카메라 전환')}><RefreshCw size={20}/></button> : <span className="round-spacer"/>}
        </> : camera.phase === 'idle' ? <>
          <button type="button" className="button button-light" onClick={() => fileInput.current?.click()}><ImagePlus size={16}/>{t('Choose a photo', '사진 선택')}</button>
          <button type="button" className="button button-primary start-camera" onClick={() => void camera.start()}><Camera size={17}/>{t('Start camera', '카메라 시작')}</button>
          <button type="button" className="button button-light" onClick={() => cameraInput.current?.click()}><Camera size={16}/>{t('Take one', '촬영')}</button>
        </> : null}
      </div>
  return <section className="look-screen" hidden={hidden} aria-label={t('Look', '보기')}>
    {real && <><input ref={fileInput} className="visually-hidden" type="file" accept="image/jpeg,image/png" aria-label={t('Choose a place, food or menu photo', '장소·음식·메뉴 사진 선택')} onChange={e => { choosePhoto(e.target.files?.[0]); e.target.value = '' }}/><input ref={cameraInput} className="visually-hidden" type="file" accept="image/jpeg,image/png" capture="environment" aria-label={t('Take a photo', '사진 촬영')} onChange={e => { choosePhoto(e.target.files?.[0]); e.target.value = '' }}/></>}
    <div className={'camera-stage camera-panel' + (live && !showPhoto ? ' is-live' : '')} aria-label={t('Camera companion', '카메라 동행')}>
      <video ref={camera.videoRef} className={live && !showPhoto ? 'camera-video' : 'camera-video camera-hidden'} autoPlay muted playsInline aria-label={t('Local camera preview', '기기 내 카메라 미리보기')} onClick={event => { void event.currentTarget.play().catch(() => {}) }}/>
      {real && live && !showPhoto && <div className="reticle" aria-hidden="true"><i/><i/><i/><i/></div>}
      {real && showPhoto && photo && <div className="photo-preview stage-photo"><img src={photo.url} alt={t('Your selected place, food or menu photo', '선택한 장소·음식·메뉴 사진')}/>{!sheet && photoActions}</div>}
      <div className="stage-top">
        <ConnectionNotices g={g}/>
        <InAppNotice g={g}/>
        {real && camera.phase !== 'idle' && <div className="stage-chips">
          {live && <label className="chip-toggle"><input type="checkbox" checked={automatic} disabled={!automaticAvailable} onChange={event => changeAutomatic(event.target.checked)}/>{t('Automatic companion', '자동동행')}</label>}
          <button type="button" className="stage-close" onClick={() => { changeAutomatic(false); camera.stop() }} aria-label={camera.phase === 'starting' ? t('Cancel camera request', '카메라 요청 취소') : t('Stop camera', '카메라 중지')}><X size={18}/></button>
        </div>}
        {real && camera.phase === 'starting' && <p className="stage-status" role="status">{t('Waiting for camera permission…', '카메라 권한을 기다리고 있어요…')}</p>}
        {real && live && <p className="stage-status" role="status">{automatic ? automaticPaused ? t('Paused while you ask, listen, or wait for an answer.', '질문·음성 입력·답변 중에는 잠시 기다려요.') : t('Looking for a change in the view… ask any time.', '장면이 바뀌면 살펴볼게요. 언제든 직접 물어보세요.') : t('Tap the shutter to freeze a photo, or just ask.', '셔터로 사진을 고정하거나 바로 물어보세요.')}</p>}
        {real && live && !automaticAvailable && <small className="stage-hint">{t('To use automatic guidance, connect your guide and release any saved photo.', '가이드에 연결하고 고정 사진을 해제하면 자동동행을 사용할 수 있어요.')}</small>}
        {camera.notice && <p className="inline-notice" role="status"><Info size={14}/>{camera.notice}</p>}
        {/* With an answer sheet up, the camera controls move to the top so the sheet never hides them. */}
        {sheet && controls}
        {sheet && real && showPhoto && <div className="photo-row">{photoActions}</div>}
      </div>
      {real && camera.phase === 'idle' && !showPhoto && <div className="stage-idle">
        <span className="stage-idle-icon"><Camera size={30}/></span>
        <h2>{t('Point your camera at anything Korean', '눈앞의 한국을 카메라로 비춰 보세요')}</h2>
        <p>{t('A palace, a sign, a dish. We tell you the story behind it — in simple words.', '궁궐, 간판, 음식까지. 그 뒤의 이야기를 쉽게 들려드려요.')}</p>
        <p className="idle-privacy"><ShieldCheck size={13}/>{t('Only photos you send leave this device.', '보낸 사진만 기기 밖으로 나가요.')}<InfoTip t={t} text={t('Only photos you take (or automatic snapshots) are sent. The live preview stays on this device.', '찍은 사진(또는 자동 스냅)만 보내요. 실시간 미리보기는 이 기기에만 남아요.')}/></p>
      </div>}
      {!real && <div className="stage-idle practice"><h2>{t('Practice itinerary', '연습 일정')}</h2><p>{t('Fictional places from the practice materials. Ask below.', '연습 자료의 가상 장소예요. 아래에서 질문해 주세요.')}</p></div>}
      {!sheet && controls}
      {captionMode && (!sheet || !sheetOpen) && <LiveCaption g={g} aboveSheet={sheet} onOpen={() => { setSheetOpen(true); requestAnimationFrame(() => document.querySelector<HTMLElement>('.answer-sheet .sheet-grab')?.focus()) }}/>}
      {sheet && <BottomSheet className="answer-sheet" open={sheetOpen} onOpenChange={setSheetOpen} t={t}><ResultDetails g={g}/></BottomSheet>}
    </div>
    <Composer g={g}/>
  </section>
}
