import { Camera, Info, Square } from 'lucide-react'
import type { Language } from './types'
import type { useCamera } from './useCamera'

type Props = {
  camera: ReturnType<typeof useCamera>; language: Language;
  automatic: boolean; automaticAvailable: boolean; paused: boolean;
  onAutomatic(enabled: boolean): void; onCapture(): void;
}
export default function CameraPanel({ camera, language, automatic, automaticAvailable, paused, onAutomatic, onCapture }: Props) {
  const t = (en: string, ko: string) => language === 'ko' ? ko : en
  return <section className="camera-panel" aria-label={t('Camera companion', '카메라 동행')}>
    <div className="camera-heading"><Camera size={17}/><strong>{t('A companion for what you see', '눈앞의 풍경과 함께하는 동행')}</strong></div>
    <p>{t('A palace, a street, a dish. Your camera preview stays on this device.', '궁궐, 골목, 음식까지. 카메라 미리보기는 내 기기에만 남아요.')}</p>
    <video ref={camera.videoRef} className={camera.phase === 'live' ? 'camera-video' : 'camera-video camera-hidden'} autoPlay muted playsInline aria-label={t('Local camera preview', '기기 내 카메라 미리보기')} onClick={event => { void event.currentTarget.play().catch(() => {}) }}/>
    <div className="camera-actions">
      {camera.phase === 'idle' ? <button className="button button-soft" onClick={() => void camera.start()}><Camera size={15}/>{t('Start camera', '카메라 시작')}</button> : <button className="button button-light" onClick={() => { onAutomatic(false); camera.stop() }}><Square size={14}/>{camera.phase === 'starting' ? t('Cancel camera request', '카메라 요청 취소') : t('Stop camera', '카메라 중지')}</button>}
      {camera.phase === 'live' && <button className="button button-soft" onClick={onCapture}><Camera size={15}/>{t('Capture a photo', '사진 고정 촬영')}</button>}
    </div>
    {camera.phase === 'starting' && <p role="status">{t('Waiting for camera permission…', '카메라 권한을 기다리고 있어요…')}</p>}
    {camera.phase === 'live' && <div className="companion-options"><label><input type="checkbox" checked={automatic} disabled={!automaticAvailable} onChange={event => onAutomatic(event.target.checked)}/>{t('Automatic companion', '자동동행')}</label><small>{t('Optional: send one sampled photo at least 20 seconds after the previous answer. This analyses photos, not a video stream. No camera audio is captured.', '선택 시 이전 답변이 끝난 뒤 최소 20초 후에 사진 한 장을 보내요. 영상 자체가 아닌 샘플 사진 분석이며 카메라 소리는 녹음하지 않아요.')}</small><p role="status">{automatic ? paused ? t('Paused while you ask, listen, or wait for an answer.', '질문·음성 입력·답변 중에는 잠시 기다려요.') : t('Automatic companion is on. You can ask a question at any time.', '자동동행 중이에요. 언제든 직접 질문할 수 있어요.') : t('Capture freezes a photo. Send it separately with your question.', '촬영하면 사진이 고정돼요. 질문을 적어 따로 보내 주세요.')}</p>{!automaticAvailable && <small>{t('To use automatic guidance, connect your guide and release any saved photo.', '가이드에 연결하고 고정 사진을 해제하면 자동동행을 사용할 수 있어요.')}</small>}</div>}
    {camera.notice && <p className="inline-notice" role="status"><Info size={14}/>{camera.notice}</p>}
  </section>
}
