import { useState } from 'react'
import { Copy, Info, ShieldCheck, Volume2, VolumeX } from 'lucide-react'
import type { Language } from '../types'
import type { StoryBlocks, Verification } from '../draftTypes'

type T = (en: string, ko: string) => string
export type Story = { name: string; name_local: string | null; blocks: StoryBlocks; verification: Verification; evidence_ids: string[]; visitor_tips?: string[] }

const BLOCKS: [keyof StoryBlocks, string, string][] = [
  ['what_it_is', 'What it is', '어떤 곳?'],
  ['why_it_matters', 'Why it matters', '왜 중요해요?'],
  ['what_to_look_for', 'What to look for', '무엇을 볼까요?'],
  ['fun_fact', 'Fun fact', '재미있는 사실'],
]
export const storyText = (story: Story) => BLOCKS.map(([key]) => story.blocks[key]).filter(Boolean).join(' ')

export function VerificationBadge({ value, t }: { value: Verification; t: T }) {
  if (value === 'model_unverified') return <span className="verify-badge unverified"><Info size={12}/>{t('Unverified · general knowledge', '확인 필요 · 일반 지식')}</span>
  return <span className="verify-badge"><ShieldCheck size={12}/>{value === 'catalog' ? t('Checked collection', '검수 자료') : t('Public source', '공개 자료')}</span>
}

/** The 30-second story: four short blocks, one Listen button. Missing blocks are omitted. */
export function StoryCard({ story, t, speaking, onListen, onStop }: { story: Story; t: T; speaking: boolean; onListen(text: string): void; onStop(): void }) {
  const text = storyText(story)
  return <article className="story-card" aria-label={t('30-second story', '30초 이야기')}>
    <span className="overline">{t('In 30 seconds', '30초 이야기')}</span>
    <div className="story-head"><div><h3>{story.name}</h3>{story.name_local && <p className="story-local">{story.name_local}</p>}</div>
      <button type="button" className={'listen-button' + (speaking ? ' playing' : '')} onClick={() => speaking ? onStop() : onListen(text)} disabled={!text} aria-label={speaking ? t('Stop listening to the story', '이야기 듣기 멈추기') : t('Listen to the story', '이야기 듣기')}>{speaking ? <VolumeX size={18}/> : <Volume2 size={18}/>}<span>{speaking ? t('Stop', '멈춤') : t('Listen', '듣기')}</span></button></div>
    <dl className="story-blocks">{BLOCKS.filter(([key]) => story.blocks[key]).map(([key, en, ko]) => <div key={key} className={'story-block block-' + key}><dt>{t(en, ko)}</dt><dd>{story.blocks[key]}</dd></div>)}</dl>
    {story.visitor_tips && story.visitor_tips.length > 0 && <ul className="story-tips">{story.visitor_tips.map(tip => <li key={tip}><Info size={12}/>{tip}</li>)}</ul>}
    <div className="story-foot"><VerificationBadge value={story.verification} t={t}/>{story.evidence_ids.length > 0 && <small>{story.evidence_ids.join(' · ')}</small>}</div>
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
