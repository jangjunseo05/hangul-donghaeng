import { useState } from 'react'
import type { ReactNode } from 'react'
import { Camera, ChevronDown, ChevronUp, Landmark, Route as RouteIcon, Shield, ShieldCheck, ShieldOff, Utensils } from 'lucide-react'
import type { Guide } from '../useGuide'
import type { Tab } from '../contract'
import { sandboxPassed, workerModelLabel } from '../sandbox'

export function TopBar({ g }: { g: Guide }) {
  const { t, health, healthFailed, language, speech, setLanguage, setStatusOpen } = g
  const choose = (next: 'en' | 'ko') => { speech.stopListening(); speech.stopReading(); setLanguage(next) }
  return <header className="top-bar">
    <a className="brand" href="#" aria-label="Hangul Donghaeng home"><span className="brand-mark">한</span><span className="brand-word">한글동행</span></a>
    <div className="header-actions">
      <SandboxBadge g={g}/>
      <button className="connection-button" aria-label={t('Connection', '연결 상태')} onClick={() => setStatusOpen(true)}><span className={'connection-dot ' + (health && !healthFailed && health.worker_connected ? 'online' : '')} /><span>{healthFailed || !health ? t('Offline', '연결 필요') : health.worker_connected ? t('Connected', '연결됨') : t('Connecting', '준비 중')}</span></button>
      <div className="language-toggle" aria-label={t('Language', '언어')}>
        <button className={language === 'en' ? 'selected' : ''} onClick={() => choose('en')} aria-pressed={language === 'en'}>EN</button>
        <button className={language === 'ko' ? 'selected' : ''} onClick={() => choose('ko')} aria-pressed={language === 'ko'}>한글</button>
      </div>
    </div>
  </header>
}

/**
 * Top-bar sandbox badge. Green only when the stored OpenShell evidence passed AND the connected worker labels itself
 * 'openshell' (both are reports, not a live check). A local-dev or unlabeled worker never shows a sandbox state.
 */
function SandboxBadge({ g }: { g: Guide }) {
  const { t, health, healthFailed, setStatusOpen } = g
  const evidence = healthFailed ? null : health?.sandbox_evidence
  const passed = sandboxPassed(evidence)
  const worker = Boolean(!healthFailed && health?.worker_connected)
  const model = worker ? workerModelLabel(health?.worker_model) : null
  const context = worker ? health?.worker_model?.run_context ?? 'unknown' : null
  const date = evidence?.captured_at?.slice(0, 10)
  const modelText = model ? model.short : t('model not reported', '모델 보고 없음')
  const evidenceText = !evidence ? t('no stored OpenShell evidence', '저장된 OpenShell 근거 없음') : passed
    ? t(`stored OpenShell evidence ${evidence.boundary_checks_passed}/${evidence.boundary_checks_total} PASS · ${evidence.worker ?? 'worker'} · ${date ?? 'date unknown'} · not a live check`, `저장된 OpenShell 근거 ${evidence.boundary_checks_passed}/${evidence.boundary_checks_total} 통과 · ${evidence.worker ?? '워커'} · ${date ?? '날짜 미상'} · 실시간 확인 아님`)
    : t(`stored boundary test incomplete ${evidence.boundary_checks_passed}/${evidence.boundary_checks_total} · ${date ?? 'date unknown'}`, `저장된 경계 테스트 미통과 ${evidence.boundary_checks_passed}/${evidence.boundary_checks_total} · ${date ?? '날짜 미상'}`)
  const [tone, main, sub, spoken] =
    !worker ? ['', evidence ? t('Stored OpenShell evidence', '저장된 OpenShell 근거') : 'OpenShell', t('No worker connected', '연결된 워커 없음'), t('No worker connected', '연결된 워커 없음')]
    : context === 'local-dev' ? [' local', t('Local worker', '로컬 워커'), t('No sandbox · ', '샌드박스 없음 · ') + modelText, t(`Local worker without a sandbox, model ${model?.id ?? 'not reported'}`, `샌드박스 없는 로컬 워커, 모델 ${model?.id ?? '보고 없음'}`)]
    : context === 'openshell' ? [passed ? ' ok' : '', 'OpenShell sandbox', t('Self-reported · ', '워커 자기 보고 · ') + modelText, t(`OpenShell sandbox as reported by the worker itself, not verified live, model ${model?.id ?? 'not reported'}`, `워커가 스스로 OpenShell이라고 보고함, 실시간 검증 아님, 모델 ${model?.id ?? '보고 없음'}`)]
    : [' local', t('Worker connected', '워커 연결됨'), t('Sandbox not reported · ', '샌드박스 미보고 · ') + modelText, t(`Worker connected, sandbox not reported, model ${model?.id ?? 'not reported'}`, `워커 연결됨, 샌드박스 미보고, 모델 ${model?.id ?? '보고 없음'}`)]
  // A local or unlabeled worker never announces the stored PASS: that record belongs to another deployment.
  const shownEvidence = tone === ' local' && evidence ? t('stored OpenShell evidence is from another deployment and does not apply to this worker', '저장된 OpenShell 근거는 다른 배포의 기록이라 이 워커에 해당하지 않음') : evidenceText
  return <button type="button" className={'sandbox-badge' + tone} onClick={() => setStatusOpen(true)}
    title={(worker ? t(`Worker label (self-reported): ${context}`, `워커 라벨(자기 보고): ${context}`) + (model ? ' · ' + model.id : '') + ' · ' : '') + shownEvidence}
    aria-label={spoken + '. ' + shownEvidence + '. ' + t('Show sandbox and connection', '샌드박스·연결 상태 보기')}>
    {tone === ' local' ? <ShieldOff size={16}/> : tone === ' ok' ? <ShieldCheck size={16}/> : <Shield size={16}/>}<span className="sb-text"><span className="sb-main">{main}</span><span className="sb-model">{sub}</span></span>
  </button>
}

export function TabBar({ tab, onTab, t }: { tab: Tab; onTab(tab: Tab): void; t: Guide['t'] }) {
  const item = (id: Tab, icon: ReactNode, label: string) => <button type="button" role="tab" aria-selected={tab === id} className={'tab-item' + (tab === id ? ' on' : '')} onClick={() => onTab(id)}>{icon}<span>{label}</span></button>
  return <nav className="tab-bar" role="tablist" aria-label={t('Sections', '메뉴')}>
    {item('landmarks', <Landmark size={21}/>, t('Landmarks', '랜드마크'))}
    {item('eat', <Utensils size={21}/>, t('Eat', '맛집'))}
    <button type="button" role="tab" aria-selected={tab === 'look'} className={'tab-item tab-look' + (tab === 'look' ? ' on' : '')} onClick={() => onTab('look')}><span className="look-fab"><Camera size={25}/></span><span>{t('Look', '보기')}</span></button>
    {item('routes', <RouteIcon size={21}/>, t('Routes', '루트'))}
  </nav>
}

/** Rounded sheet with a grab handle that collapses to its header. */
export function BottomSheet({ title, children, className = '', defaultOpen = true, open: controlled, onOpenChange, t }: { title?: ReactNode; children: ReactNode; className?: string; defaultOpen?: boolean; open?: boolean; onOpenChange?(open: boolean): void; t: Guide['t'] }) {
  const [own, setOwn] = useState(defaultOpen)
  const open = controlled ?? own
  const setOpen = (next: (value: boolean) => boolean) => { const value = next(open); setOwn(value); onOpenChange?.(value) }
  return <section className={'bottom-sheet ' + className + (open ? ' is-open' : ' is-collapsed')}>
    <button type="button" className="sheet-grab" aria-expanded={open} aria-label={open ? t('Collapse sheet', '시트 접기') : t('Expand sheet', '시트 펼치기')} onClick={() => setOpen(value => !value)}><span />{open ? <ChevronDown size={14}/> : <ChevronUp size={14}/>}</button>
    {title && <div className="sheet-title">{title}</div>}
    <div className="sheet-body">{children}</div>
  </section>
}
