import { ArrowRight, BookOpen, Check, FileSearch, Info, RotateCcw, ShieldCheck, WifiOff, X } from 'lucide-react'
import type { Guide } from '../useGuide'
import { MODEL_LABEL, sandboxPassed } from '../sandbox'
import { ProbeCard } from './ProbeCard'

export function StatusDialog({ g, onReview }: { g: Guide; onReview?(): void }) {
  const { t, dialog, setStatusOpen, health, healthFailed, session, checkedAt, reconnect, changeMode, mode } = g
  return <dialog ref={dialog} className="status-dialog" onClose={() => setStatusOpen(false)} onClick={e => { if (e.target === e.currentTarget) setStatusOpen(false) }}><div className="dialog-heading"><h2>{t('Sandbox & connection', '샌드박스 · 연결 상태')}</h2><button className="icon-button" onClick={() => setStatusOpen(false)} aria-label={t('Close status', '상태 닫기')}><X size={19}/></button></div><SandboxEvidenceCard g={g}/><p className="session-blocked"><span className="live-tag">{t('This session · live', '이번 세션 · 실시간')}</span>{t(`Broker rejected ${g.sessionBlocked} app call${g.sessionBlocked === 1 ? '' : 's'} this session`, `이번 세션 브로커 거부 ${g.sessionBlocked}건`)}</p><ProbeCard g={g}/>{onReview && <button type="button" className="button button-soft review-open" onClick={() => { setStatusOpen(false); onReview() }}><FileSearch size={15}/>{t('Open source review mode', '자료 검토 모드 열기')}<ArrowRight size={14}/></button>}<dl className="health-list">{[[t('Service reachable', '서비스 연결'), Boolean(health && !healthFailed)], [t('Browser session', '브라우저 세션'), Boolean(session)], [t('Worker connected', 'worker 연결'), Boolean(!healthFailed && health?.worker_connected)], [t('Hosted API configuration', '호스팅 API 설정'), Boolean(!healthFailed && health?.model_configured)], [t('Live sandbox check of this worker', '이 워커의 실시간 샌드박스 확인'), Boolean(!healthFailed && health?.sandbox_verified)]].map(([label, ok]) => <div key={String(label)}><dt>{label}</dt><dd className={ok ? 'health-ok' : 'health-wait'}>{ok ? <Check size={13}/> : <Info size={13}/>} {ok ? t('Reported', '보고됨') : t('Not confirmed', '미확인')}</dd></div>)}</dl><small>{t('Last checked', '마지막 확인')}: {checkedAt || t('Not yet', '아직 없음')}</small><button className="button button-soft dialog-reconnect" onClick={() => void reconnect()}><RotateCcw size={15}/>{t('Refresh connection', '연결 새로고침')}</button><div className="privacy-note"><ShieldCheck size={18}/><p>{t('When you send a question or enable automatic companion, sampled photos are sent for analysis; the camera preview stays on this device. Voice input may use your browser’s external speech service. Map tiles are requested from OpenStreetMap. Location is used after you choose or allow it.', '질문을 보내거나 자동동행을 켜면 샘플 사진을 분석을 위해 전송해요. 카메라 미리보기는 내 기기에만 남아요. 음성 인식은 브라우저의 외부 서비스를 사용할 수 있고, 지도는 OpenStreetMap 타일을 받아요. 위치는 직접 선택하거나 허용할 때 사용해요.')}</p></div><button className="practice-link" onClick={() => changeMode(mode === 'real_place' ? 'fictional_task' : 'real_place')}><BookOpen size={15}/>{mode === 'real_place' ? t('Try the fictional practice itinerary', '가상 자료로 연습 일정 만들기') : t('Return to real-place exploration', '실제 장소 여행으로 돌아가기')}<ArrowRight size={14}/></button></dialog>
}
/** Effective policy summary from stored OpenShell deployment evidence; past tense, labeled with worker and date, never a live check. */
function SandboxEvidenceCard({ g }: { g: Guide }) {
  const { t, health, healthFailed, language } = g
  const evidence = healthFailed ? null : health?.sandbox_evidence
  const model = <p className="sandbox-model">{t('Model', '모델')}: {MODEL_LABEL.full} <span>({t('configuration per README, not observed by the broker', 'README 기준 구성 · 브로커 관측값 아님')})</span></p>
  if (!evidence) return <div className="sandbox-card"><div className="sandbox-card-head"><ShieldCheck size={17}/><strong>OpenShell</strong></div><p>{t('No stored sandbox evidence was reported.', '저장된 샌드박스 근거가 보고되지 않았어요.')}</p>{model}</div>
  const date = evidence.captured_at && Number.isFinite(Date.parse(evidence.captured_at)) ? new Date(evidence.captured_at).toLocaleDateString(language === 'ko' ? 'ko-KR' : 'en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : t('date unknown', '날짜 미상')
  const passed = sandboxPassed(evidence)
  const worker = evidence.worker ?? t('worker unknown', 'worker 미상')
  const allow = evidence.policy_network_allow ?? []
  return <section className={'sandbox-card' + (passed ? ' ok' : '')} aria-label={t('OpenShell effective policy', 'OpenShell 실효 정책')}>
    <div className="sandbox-card-head">{passed ? <ShieldCheck size={17}/> : <Info size={17}/>}<strong>{evidence.runtime}</strong><span className="sandbox-score">{t('Boundary test', '경계 테스트')} {evidence.boundary_checks_passed}/{evidence.boundary_checks_total} {passed ? 'PASS' : t('incomplete', '미통과')}</span></div>
    <p className="stored-tag">{t(`Stored evidence · recorded ${date} · not a live check`, `저장된 근거 · ${date} 기록 · 실시간 확인 아님`)}</p>
    <div className="policy-block">
      <h3>{t(`Stored policy for ${worker}`, `${worker}에 저장된 정책`)} <span className={'policy-state' + (evidence.policy_loaded ? ' ok' : '')}>{evidence.policy_loaded ? t('load confirmed', '적용 확인') : t('recorded only', '기록만 있음')}</span></h3>
      {allow.length > 0 && <><p className="policy-label">{t(`Network allowed (${allow.length})`, `네트워크 허용 ${allow.length}건`)}</p><ul className="policy-chips">{allow.map(rule => <li key={rule}><code>{rule}</code></li>)}</ul></>}
      <p className="policy-deny"><ShieldCheck size={12}/>{allow.length > 0 ? t('Everything not listed was denied by default.', '목록에 없는 요청은 기본적으로 모두 차단됐어요.') : t('Network allow-list not reported.', '네트워크 허용 목록이 보고되지 않았어요.')}</p>
      {(evidence.policy_read_write?.length || evidence.policy_read_only?.length) ? <p className="policy-fs">{t('Writable', '쓰기 가능')}: <code>{(evidence.policy_read_write ?? []).join(' ')}</code>{evidence.policy_read_only?.length ? <> · {t('read-only', '읽기 전용')} {evidence.policy_read_only.length}{t(' paths', '개 경로')}</> : null}</p> : null}
      {evidence.policy_hash && <p className="policy-hash">{t('Policy hash', '정책 해시')} <code>{evidence.policy_hash.slice(0, 12)}</code></p>}
    </div>
    <div className="policy-block">
      <h3>{t(`Boundary test (probe sandbox ${evidence.boundary_sandbox ?? 'unnamed'})`, `경계 테스트 (probe 샌드박스 ${evidence.boundary_sandbox ?? '이름 미상'})`)}</h3>
      <p>{passed ? t(`All ${evidence.boundary_checks_total} recorded checks passed.`, `기록된 ${evidence.boundary_checks_total}개 항목이 모두 통과했어요.`) : t(`${evidence.boundary_checks_passed} of ${evidence.boundary_checks_total} recorded checks passed.`, `기록된 ${evidence.boundary_checks_total}개 중 ${evidence.boundary_checks_passed}개 통과했어요.`)}</p>
    </div>
    {model}
  </section>
}
export function ConnectionNotices({ g }: { g: Guide }) {
  const { t, mode, changeMode, healthFailed, session, reconnect } = g
  return <>
      {mode === 'fictional_task' && <div className="practice-banner"><BookOpen size={16}/><span>{t('Practice itinerary · fictional places, no real-world map.', '연습 일정 · 가상의 장소이며 실제 지도와 연결하지 않아요.')}</span><button onClick={() => changeMode('real_place')}>{t('Back to explore', '여행으로 돌아가기')}</button></div>}
      {(healthFailed || !session) && <div className="connection-notice" role="status"><WifiOff size={16}/><span>{t('Your guide is not connected yet. Your photo stays on this device until you ask.', '아직 가이드에 연결되지 않았어요. 질문하기 전에는 사진을 보내지 않아요.')}</span><button onClick={() => void reconnect()}><RotateCcw size={13}/>{t('Reconnect', '다시 연결')}</button></div>}
  </>
}
