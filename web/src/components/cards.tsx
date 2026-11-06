import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowUpRight, CalendarClock, Copy, Info, Lightbulb, Scale, ShieldCheck, Volume2, VolumeX } from 'lucide-react'
import type { Evidence, Language } from '../types'
import type { CardSource, StoryBlock, StoryBlocks, Verification } from '../contract'
import { safeSourceUrl } from '../api'
import { freshness } from '../freshness'

type T = (en: string, ko: string) => string
/** A LandmarkCard, or a partial story built from older results (missing blocks are simply not shown). */
export type Story = { name: string; name_local?: string | null; blocks: Partial<Record<keyof StoryBlocks, StoryBlock | null>>; visit_note?: StoryBlock | null; verification: Verification; evidence_ids: string[]; sources?: CardSource[] }

const BLOCKS: [keyof StoryBlocks, string, string][] = [
  ['what_it_is', 'What it is', '어떤 곳?'],
  ['why_it_matters', 'Why it matters', '왜 중요해요?'],
  ['what_to_look_for', 'What to look for', '무엇을 볼까요?'],
  ['fun_fact', 'Fun fact', '재미있는 사실'],
]
export const storyText = (story: Story) => BLOCKS.map(([key]) => story.blocks[key]?.text).filter(Boolean).join(' ')

export function VerificationBadge({ value, t, compact = false }: { value: Verification; t: T; compact?: boolean }) {
  if (value === 'model_unverified') return <span className="verify-badge unverified" title={t('Unverified — general knowledge, please double-check', '확인 필요 — 일반 지식이라 다시 확인해 주세요')}><Info size={12}/>{compact ? t('Unverified', '확인 필요') : t('Unverified — general knowledge, please double-check', '확인 필요 — 일반 지식이라 다시 확인해 주세요')}</span>
  return <span className="verify-badge"><ShieldCheck size={12}/>{value === 'catalog' ? t('Checked source', '검수 자료') : t('Public source', '공개 자료')}</span>
}

const hostOf = (url: string) => { try { return new URL(url).hostname } catch { return url } }
const WIKI_LICENSE = 'https://creativecommons.org/licenses/by-sa/4.0/'
function wikiTitle(url: string | undefined) {
  if (!url) return null
  try { const path = new URL(url).pathname.split('/').pop(); return path ? decodeURIComponent(path).replace(/_/g, ' ') : null } catch { return null }
}
/**
 * Source line for a block (research phase2 §4). Wikipedia: link + licence only — the source text is never quoted on screen.
 * Card `sources` (URL/title per cited id, contract M2) win; otherwise Result/nearby `evidence` URLs, then prefix labels.
 */
export function SourceLine({ ids, evidence, sources, t }: { ids: string[]; evidence?: Evidence[]; sources?: CardSource[]; t: T }) {
  if (!ids.length) return null
  const parts: ReactNode[] = []
  const seen = new Set<string>()
  const link = (href: string | undefined, label: string) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{label}<ArrowUpRight size={10}/></a> : label
  for (const id of ids) {
    const prefix = id.split(':')[0]
    const source = sources?.find(item => item.id === id)
    const record = evidence?.find(item => item.id === id)
    const href = source ? safeSourceUrl(source.url) : record ? safeSourceUrl(record.source) : undefined
    if (prefix === 'wikipedia') {
      const title = source?.title ?? wikiTitle(href)
      const key = 'wiki:' + (href ?? title ?? id)
      if (seen.has(key)) continue
      seen.add(key)
      parts.push(<span key={key}>{t('Source: Wikipedia', '출처: 위키백과')}{title && <> {link(href, t(`“${title}”`, `「${title}」`))}</>}, <a href={WIKI_LICENSE} target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>. {t('Text adapted.', '내용을 쉽게 고쳐 썼어요.')}</span>)
    } else if (prefix === 'osm') {
      if (seen.has('osm')) continue
      seen.add('osm')
      parts.push(<span key="osm"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">{t('© OpenStreetMap contributors', '© OpenStreetMap 기여자')}</a></span>)
    } else if (source) {
      const key = 'src:' + source.url + (source.title ?? '')
      if (seen.has(key)) continue
      seen.add(key)
      parts.push(<span key={key}>{t('Source: ', '출처: ')}{link(href, source.title ?? hostOf(source.url))}</span>)
    } else {
      const label = prefix === 'visitseoul' || prefix === 'visitkorea' ? t('Source: Visit Seoul / Korea Tourism Organization', '출처: 서울관광재단 / 한국관광공사')
        : prefix === 'seoul' ? t('Source: Seoul Metropolitan Government notice', '출처: 서울시 안내') : id
      if (seen.has('label:' + label)) continue
      seen.add('label:' + label)
      parts.push(<span key={'label:' + label}>{link(href, label)}</span>)
    }
  }
  return <small className="source-line">{parts}</small>
}

function Block({ label, block, t, evidence, sources }: { label: string; block: StoryBlock; t: T; evidence?: Evidence[]; sources?: CardSource[] }) {
  return <div className={'story-block' + (block.verification === 'model_unverified' ? ' is-unverified' : '')}>
    <dt>{label}{block.analogy && <span className="analogy-tag" title={t('An explanatory comparison, not a fact', '사실이 아니라 이해를 돕는 비유예요')}><Lightbulb size={11}/>{t('analogy', '비유')}</span>}</dt>
    <dd>{block.text}{block.verification === 'model_unverified' && <VerificationBadge value="model_unverified" t={t}/>}<SourceLine ids={block.evidence_ids} evidence={evidence} sources={sources} t={t}/></dd>
  </div>
}

/** The 30-second story: four short blocks with per-block verification, one Listen button. */
export function StoryCard({ story, t, speaking, onListen, onStop, evidence, fixture }: { story: Story; t: T; speaking: boolean; onListen(text: string): void; onStop(): void; evidence?: Evidence[]; fixture?: boolean }) {
  const text = storyText(story)
  return <article className="story-card" aria-label={t('30-second story', '30초 이야기')}>
    <span className="overline">{t('In 30 seconds', '30초 이야기')}</span>
    <div className="story-head"><div><h3>{story.name}</h3>{story.name_local && <p className="story-local">{story.name_local}</p>}</div>
      <button type="button" className={'listen-button' + (speaking ? ' playing' : '')} onClick={() => speaking ? onStop() : onListen(text)} disabled={!text} aria-label={speaking ? t('Stop listening to the story', '이야기 듣기 멈추기') : t('Listen to the story', '이야기 듣기')}>{speaking ? <VolumeX size={18}/> : <Volume2 size={18}/>}<span>{speaking ? t('Stop', '멈춤') : t('Listen', '듣기')}</span></button></div>
    <dl className="story-blocks">{BLOCKS.map(([key, en, ko]) => { const block = story.blocks[key]; return block ? <Block key={key} label={t(en, ko)} block={block} t={t} evidence={evidence} sources={story.sources}/> : null })}</dl>
    {story.visit_note && <div className="visit-note"><CalendarClock size={14}/><div><strong>{t('Before you go', '방문 전 확인')}</strong><p>{story.visit_note.text}</p>{story.visit_note.verification === 'model_unverified' && <VerificationBadge value="model_unverified" t={t}/>}<SourceLine ids={story.visit_note.evidence_ids} evidence={evidence} sources={story.sources} t={t}/></div></div>}
    <div className="story-foot"><VerificationBadge value={story.verification} t={t} compact/>{fixture && <span className="fixture-tag">{t('Contract example (fixture)', '계약 예시(fixture)')}</span>}</div>
  </article>
}

/** A Korean sentence the traveler can show or play. Nothing is sent or ordered. */
export function PhraseCard({ ko, gloss, t, disabled, onListen, language }: { ko: string; gloss?: string | null; t: T; disabled?: boolean; onListen(text: string, lang: Language): void; language: Language }) {
  const [notice, setNotice] = useState('')
  async function copy() {
    try { await navigator.clipboard.writeText(ko); setNotice(t('Copied!', '복사했어요!')) }
    catch { setNotice(t('Please select and copy the sentence.', '문장을 선택해 복사해 주세요.')) }
  }
  return <div className="phrase-card">
    <small>{t('Show this or play it', '보여주거나 들려주세요')}</small>
    <div className="phrase-row"><p lang="ko">{ko}</p><div>
      <button type="button" className="icon-button" disabled={disabled} onClick={() => onListen(ko, 'ko')} aria-label={t('Play Korean phrase', '한국어 문장 듣기')}><Volume2 size={17}/></button>
      <button type="button" className="icon-button" disabled={disabled} onClick={() => void copy()} aria-label={t('Copy Korean phrase', '한국어 문장 복사')}><Copy size={17}/></button></div></div>
    {gloss && language === 'en' && <small className="phrase-gloss">“{gloss}”</small>}
    {notice && <span className="copy-notice" role="status">{notice}</span>}
  </div>
}

/** Short label for a cited record: host for URLs, otherwise the id. */
const recordLabel = (id: string, evidence: Evidence[]) => { const record = evidence.find(item => item.id === id); const href = record && safeSourceUrl(record.source); return href ? hostOf(href).replace(/^www\./, '') : record?.source || id }

export function FreshnessBadge({ asOf, reference, type, checkedOn, t }: { asOf: string | null; reference: string; type: Evidence['type']; checkedOn?: string; t: T }) {
  if (type === 'live_statement') return <span className="fresh-badge live">{t('On-site statement', '현장 발언')}{asOf ? ' · ' + asOf : ''}</span>
  if (type === 'example') return <span className="fresh-badge example">{t('Example', '예시')}</span>
  const { level, months } = freshness(asOf, reference)
  // No source date: show when the team last checked it (a retrieval date, never a publication date), neutral color.
  if (asOf == null && checkedOn) return <span className="fresh-badge checked" title={t('The source states no date. This is when our team last retrieved and checked it.', '출처에 날짜가 없어요. 우리 팀이 마지막으로 조회·확인한 날짜예요.')}>{t('Checked ', '확인일 ')}{checkedOn}</span>
  if (level === 'unknown' || months === null) return <span className="fresh-badge unknown">{t('Date not provided', '날짜 미상')}</span>
  const age = months < 1 ? t('<1 mo ago', '1개월 이내') : months < 24 ? t(`${months} mo ago`, `${months}개월 전`) : t(`${Math.floor(months / 12)} yr ago`, `${Math.floor(months / 12)}년 전`)
  return <span className={'fresh-badge ' + level} title={asOf ?? undefined}>{level === 'stale' && <Info size={10}/>}{age}</span>
}

/** Trust card: conflicts resolved (A vs B → kept, why) and per-source freshness, shown outside any disclosure. */
export function TrustCard({ evidence, conflicts, reference, checked = false, observed = {}, t }: { evidence: Evidence[]; conflicts: { evidence_ids: string[]; decision: string; reason: string }[]; reference: string; checked?: boolean; observed?: Record<string, string>; t: T }) {
  if (!evidence.length && !conflicts.length) return <p className="trust-empty">{t('No source was provided for this answer.', '이 답변에는 출처가 제공되지 않았어요.')}</p>
  return <section className="trust-card" aria-label={t('Sources and conflicts', '출처와 충돌 판정')}>
    <div className="trust-head"><ShieldCheck size={15}/><strong>{t('Why you can trust this', '믿을 수 있는 이유')}</strong>{checked && <span className="shield-tag"><ShieldCheck size={10}/>{t('broker-checked', '브로커 검증')}</span>}<small>{t(`${evidence.length} sources`, `출처 ${evidence.length}`)}{conflicts.length > 0 && t(` · ${conflicts.length} conflict${conflicts.length > 1 ? 's' : ''}`, ` · 충돌 ${conflicts.length}`)}</small></div>
    {conflicts.map((conflict, index) => {
      const [a, ...rest] = conflict.evidence_ids
      return <div className="conflict-row" key={index}>
        <div className="conflict-vs"><Scale size={13}/><span>{a ? recordLabel(a, evidence) : '?'}</span>{rest.length > 0 && <><i>vs</i><span>{rest.map(id => recordLabel(id, evidence)).join(', ')}</span></>}</div>
        <p><b>{t('Kept: ', '채택: ')}</b>{conflict.decision}</p>
        <small>{t('Why: ', '이유: ')}{conflict.reason}</small>
      </div>
    })}
    <ul className="trust-sources">{evidence.map(item => {
      const href = safeSourceUrl(item.source)
      return <li key={item.id}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{hostOf(href).replace(/^www\./, '')}<ArrowUpRight size={11}/></a> : <span className="source-text">{item.source}</span>}<small className="src-type">{item.type === 'document' ? t('Document', '문서') : ''}</small><FreshnessBadge asOf={item.as_of} reference={reference} type={item.type} checkedOn={Object.hasOwn(observed, item.id) ? observed[item.id] : undefined} t={t}/></li>
    })}</ul>
  </section>
}

/** One-line notes keep the detail behind an (i). The text is always the button's description; tapping shows it as a bubble pinned above the tab bar. */
export function InfoTip({ text, t }: { text: string; t: T }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const root = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [open])
  return <span className="info-tip" ref={root}><button type="button" aria-label={t('More information', '자세히')} aria-expanded={open} aria-describedby={id} onClick={() => setOpen(value => !value)}><Info size={13}/></button><span id={id} className={open ? 'info-tip-bubble' : 'visually-hidden'} role={open ? 'status' : undefined}>{text}</span></span>
}
