import { useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowUpRight, CalendarClock, Copy, Info, Lightbulb, ShieldCheck, Volume2, VolumeX } from 'lucide-react'
import type { Evidence, Language } from '../types'
import type { StoryBlock, StoryBlocks, Verification } from '../contract'
import { safeSourceUrl } from '../api'

type T = (en: string, ko: string) => string
/** A LandmarkCard, or a partial story built from older results (missing blocks are simply not shown). */
export type Story = { name: string; name_local?: string | null; blocks: Partial<Record<keyof StoryBlocks, StoryBlock | null>>; visit_note?: StoryBlock | null; verification: Verification; evidence_ids: string[] }

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

const WIKI_LICENSE = 'https://creativecommons.org/licenses/by-sa/4.0/'
function wikiTitle(url: string | undefined) {
  if (!url) return null
  try { const path = new URL(url).pathname.split('/').pop(); return path ? decodeURIComponent(path).replace(/_/g, ' ') : null } catch { return null }
}
/**
 * Source line for a block (research phase2 §4). Wikipedia: link + licence only — the source text is never quoted on screen.
 */
export function SourceLine({ ids, evidence, t }: { ids: string[]; evidence?: Evidence[]; t: T }) {
  if (!ids.length) return null
  const prefixes = new Set(ids.map(id => id.split(':')[0]))
  const parts: ReactNode[] = []
  if (prefixes.has('wikipedia')) {
    const record = evidence?.find(item => ids.includes(item.id) && item.id.startsWith('wikipedia:'))
    const href = record ? safeSourceUrl(record.source) : undefined
    const title = wikiTitle(href)
    parts.push(<span key="wiki">{t('Source: Wikipedia', '출처: 위키백과')}{title && <> {href ? <a href={href} target="_blank" rel="noopener noreferrer">{t(`“${title}”`, `「${title}」`)}<ArrowUpRight size={10}/></a> : t(`“${title}”`, `「${title}」`)}</>}, <a href={WIKI_LICENSE} target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>. {t('Text adapted.', '내용을 쉽게 고쳐 썼어요.')}</span>)
  }
  if (prefixes.has('visitseoul') || prefixes.has('visitkorea')) parts.push(<span key="official">{t('Source: Visit Seoul / Korea Tourism Organization', '출처: 서울관광재단 / 한국관광공사')}</span>)
  if (prefixes.has('seoul')) parts.push(<span key="seoul">{t('Source: Seoul Metropolitan Government notice', '출처: 서울시 안내')}</span>)
  if (prefixes.has('osm')) parts.push(<span key="osm"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">{t('© OpenStreetMap contributors', '© OpenStreetMap 기여자')}</a></span>)
  const other = ids.filter(id => !['wikipedia', 'visitseoul', 'visitkorea', 'seoul', 'osm'].includes(id.split(':')[0]))
  if (other.length) parts.push(<span key="other">{other.join(' · ')}</span>)
  return <small className="source-line">{parts}</small>
}

function Block({ label, block, t, evidence }: { label: string; block: StoryBlock; t: T; evidence?: Evidence[] }) {
  return <div className={'story-block' + (block.verification === 'model_unverified' ? ' is-unverified' : '')}>
    <dt>{label}{block.analogy && <span className="analogy-tag" title={t('An explanatory comparison, not a fact', '사실이 아니라 이해를 돕는 비유예요')}><Lightbulb size={11}/>{t('analogy', '비유')}</span>}</dt>
    <dd>{block.text}{block.verification === 'model_unverified' && <VerificationBadge value="model_unverified" t={t}/>}<SourceLine ids={block.evidence_ids} evidence={evidence} t={t}/></dd>
  </div>
}

/** The 30-second story: four short blocks with per-block verification, one Listen button. */
export function StoryCard({ story, t, speaking, onListen, onStop, evidence, fixture }: { story: Story; t: T; speaking: boolean; onListen(text: string): void; onStop(): void; evidence?: Evidence[]; fixture?: boolean }) {
  const text = storyText(story)
  return <article className="story-card" aria-label={t('30-second story', '30초 이야기')}>
    <span className="overline">{t('In 30 seconds', '30초 이야기')}</span>
    <div className="story-head"><div><h3>{story.name}</h3>{story.name_local && <p className="story-local">{story.name_local}</p>}</div>
      <button type="button" className={'listen-button' + (speaking ? ' playing' : '')} onClick={() => speaking ? onStop() : onListen(text)} disabled={!text} aria-label={speaking ? t('Stop listening to the story', '이야기 듣기 멈추기') : t('Listen to the story', '이야기 듣기')}>{speaking ? <VolumeX size={18}/> : <Volume2 size={18}/>}<span>{speaking ? t('Stop', '멈춤') : t('Listen', '듣기')}</span></button></div>
    <dl className="story-blocks">{BLOCKS.map(([key, en, ko]) => { const block = story.blocks[key]; return block ? <Block key={key} label={t(en, ko)} block={block} t={t} evidence={evidence}/> : null })}</dl>
    {story.visit_note && <div className="visit-note"><CalendarClock size={14}/><div><strong>{t('Before you go', '방문 전 확인')}</strong><p>{story.visit_note.text}</p>{story.visit_note.verification === 'model_unverified' && <VerificationBadge value="model_unverified" t={t}/>}<SourceLine ids={story.visit_note.evidence_ids} evidence={evidence} t={t}/></div></div>}
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
