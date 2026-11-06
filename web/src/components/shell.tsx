import { useState } from 'react'
import type { ReactNode } from 'react'
import { Camera, ChevronDown, ChevronUp, Landmark, Route as RouteIcon, ShieldCheck, Utensils } from 'lucide-react'
import type { Guide } from '../useGuide'
import type { Tab } from '../contract'
import { MODEL_LABEL, sandboxPassed } from '../sandbox'

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

/** OpenShell badge: stored deployment evidence (not a live check) + the configured model; opens the policy summary. */
function SandboxBadge({ g }: { g: Guide }) {
  const { t, health, healthFailed, setStatusOpen } = g
  const evidence = healthFailed ? null : health?.sandbox_evidence
  const passed = sandboxPassed(evidence)
  const date = evidence?.captured_at?.slice(0, 10)
  return <button type="button" className={'sandbox-badge' + (passed ? ' ok' : '')} onClick={() => setStatusOpen(true)}
    title={!evidence ? t('No stored OpenShell evidence', '저장된 OpenShell 근거 없음') : passed ? t(`Stored OpenShell evidence · ${evidence.worker ?? 'worker'} · ${date ?? 'date unknown'} · not a live check`, `저장된 OpenShell 근거 · ${evidence.worker ?? '워커'} · ${date ?? '날짜 미상'} · 실시간 확인 아님`) : t(`Stored boundary test ${evidence.boundary_checks_passed}/${evidence.boundary_checks_total} · incomplete · ${date ?? 'date unknown'}`, `저장된 경계 테스트 ${evidence.boundary_checks_passed}/${evidence.boundary_checks_total} · 미통과 · ${date ?? '날짜 미상'}`)}
    aria-label={(!evidence ? t('OpenShell sandbox, no stored evidence', 'OpenShell 샌드박스, 저장된 근거 없음') : passed ? t(`OpenShell sandbox, stored boundary test ${evidence.boundary_checks_passed} of ${evidence.boundary_checks_total} passed`, `OpenShell 샌드박스, 저장된 경계 테스트 ${evidence.boundary_checks_total}개 중 ${evidence.boundary_checks_passed}개 통과`) : t(`OpenShell sandbox, stored boundary test incomplete, ${evidence.boundary_checks_passed} of ${evidence.boundary_checks_total}`, `OpenShell 샌드박스, 저장된 경계 테스트 미통과 ${evidence.boundary_checks_total}개 중 ${evidence.boundary_checks_passed}개`)) + ` · ${MODEL_LABEL.short} · ${MODEL_LABEL.host}. ` + t('Show policy', '정책 보기')}>
    <ShieldCheck size={16}/><span className="sb-text"><span className="sb-main">OpenShell sandbox</span><span className="sb-model">{MODEL_LABEL.short} · {MODEL_LABEL.host}</span></span>
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
