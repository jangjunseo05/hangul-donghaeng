import { useState } from 'react'
import type { ReactNode } from 'react'
import { BookOpen, Camera, ChevronDown, ChevronUp, Landmark, Route as RouteIcon, Utensils } from 'lucide-react'
import type { Guide } from '../useGuide'
import type { Tab } from '../draftTypes'

export function TopBar({ g }: { g: Guide }) {
  const { t, health, healthFailed, language, speech, setLanguage, setStatusOpen } = g
  const choose = (next: 'en' | 'ko') => { speech.stopListening(); speech.stopReading(); setLanguage(next) }
  return <header className="top-bar">
    <a className="brand" href="#" aria-label="Hangul Donghaeng home"><span className="brand-mark">한</span><span className="brand-word">한글동행</span></a>
    <div className="header-actions">
      <button className="connection-button" aria-label={t('Connection', '연결 상태')} onClick={() => setStatusOpen(true)}><span className={'connection-dot ' + (health && !healthFailed && health.worker_connected ? 'online' : '')} /><span>{healthFailed || !health ? t('Offline', '연결 필요') : health.worker_connected ? t('Connected', '연결됨') : t('Connecting', '준비 중')}</span></button>
      <div className="language-toggle" aria-label={t('Language', '언어')}>
        <button className={language === 'en' ? 'selected' : ''} onClick={() => choose('en')} aria-pressed={language === 'en'}>EN</button>
        <button className={language === 'ko' ? 'selected' : ''} onClick={() => choose('ko')} aria-pressed={language === 'ko'}>한글</button>
      </div>
    </div>
  </header>
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
export function BottomSheet({ title, children, className = '', defaultOpen = true, t }: { title?: ReactNode; children: ReactNode; className?: string; defaultOpen?: boolean; t: Guide['t'] }) {
  const [open, setOpen] = useState(defaultOpen)
  return <section className={'bottom-sheet ' + className + (open ? ' is-open' : ' is-collapsed')}>
    <button type="button" className="sheet-grab" aria-expanded={open} aria-label={open ? t('Collapse sheet', '시트 접기') : t('Expand sheet', '시트 펼치기')} onClick={() => setOpen(value => !value)}><span />{open ? <ChevronDown size={14}/> : <ChevronUp size={14}/>}</button>
    {title && <div className="sheet-title">{title}</div>}
    <div className="sheet-body">{children}</div>
  </section>
}

export function FixtureNote({ t }: { t: Guide['t'] }) {
  return <p className="fixture-note"><BookOpen size={12}/>{t('Development fixture · contract pending (M2)', '개발용 예시 데이터 · 계약 확정 전(M2)')}</p>
}
