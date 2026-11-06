import { useEffect, useRef, useState } from 'react'
import { ShieldCheck, ShieldX } from 'lucide-react'
import type { JobStage } from '../contract'
import type { GuideResult, TraceEvent } from '../types'
import { blockedCount, formatSeconds, isBlocked, phaseRows, PHASES, reachedPhase, totalMs as brokerTotal } from '../trace'
import type { TracePhase } from '../trace'

type T = (en: string, ko: string) => string
const PHASE_LABEL: Record<TracePhase, [string, string]> = {
  observe: ['Observe', '관찰'], candidates: ['Candidates', '후보 찾기'], tools: ['Tools', '도구 호출'], judge: ['Weigh sources', '근거 판단'], answer: ['Answer', '답변'],
}
const EVENT_LABEL: Record<string, [string, string]> = {
  request_accepted: ['Request received', '요청 접수'], job_claimed: ['Worker picked up the job', '워커가 작업 시작'],
  observing: ['Photo analysis (worker-reported)', '사진 분석 (워커 보고)'], matching: ['Matching candidates', '후보 대조'],
  landmark_candidates: ['Landmark candidates', '랜드마크 후보'], catalog_search: ['Curated catalog', '수록 장소 목록'],
  osm_live_search: ['OpenStreetMap live', 'OpenStreetMap 실시간'], wikipedia: ['Wikipedia', '위키백과'],
  grounding_check: ['Broker source check', '브로커 근거 검증'], writing: ['Writing the answer', '답변 작성'],
  result_saved: ['Answer saved', '답변 저장'], worker_failed: ['Worker failed', '워커 실패'], trace_truncated: ['Trace truncated', '기록 일부 생략'],
  review_sources: ['Sort the sources (rules)', '자료 분류 (규칙)'], canary_received: ['Canary route hit at the broker', '브로커 canary 경로 수신'],
}
/** Broker-mediated steps carry a shield: the broker ran the tool or check itself, at the trust boundary. */
const SHIELD: Partial<Record<TraceEvent['kind'], [string, string]>> = { tool: ['via broker', '브로커 경유'], check: ['broker check', '브로커 검사'] }

function detailText(detail: string | null, t: T) {
  if (!detail) return null
  if (detail === 'photo normalized, EXIF removed') return t('photo normalized · EXIF removed', '사진 정규화 · EXIF 제거')
  return t(detail.replace(/(^|\D)1 (result|candidate|record|source|conflict)s\b/g, '$11 $2'), detail.replace(/(\d+) results?/g, '결과 $1건').replace(/(\d+) candidates?/g, '후보 $1개').replace(/(\d+) records?/g, '기록 $1건').replace(/(\d+) sources?/g, '출처 $1곳').replace(/(\d+) conflicts?/g, '충돌 $1건'))
}

function useElapsed(startedAt: number, running: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [running, startedAt])
  return Math.max(0, now - startedAt)
}

/**
 * "How it decided": the broker-recorded trace grouped as observe → candidates → tools → weigh → answer,
 * with per-phase time and shield badges. Live while a request runs (progress = phases reached, no fixed estimate).
 */
export function ReasoningTimeline({ events, t, review = false, live = false, follow = false, startedAt = 0, stage = null, totalMs, result }: { events: TraceEvent[]; t: T; review?: boolean; live?: boolean; follow?: boolean; startedAt?: number; stage?: JobStage | null; totalMs?: number; result?: GuideResult | null }) {
  const elapsed = useElapsed(startedAt, live)
  const reached = reachedPhase(events, stage)
  // Live: keep the running phase in view inside the scrolling sheet.
  const list = useRef<HTMLOListElement>(null)
  useEffect(() => {
    if (!live || !follow) return
    list.current?.querySelector('.reasoning-step.now')?.scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [live, follow, reached])
  // While live, the running step lasts until "now" (client clock; slightly over-counts by the upload time).
  const rows = phaseRows(events, live ? elapsed : null)
  const total = live ? Math.max(elapsed, brokerTotal(events)) : brokerTotal(events) || (totalMs ?? 0)
  if (!live && events.length === 0) return null
  const progress = live ? Math.min(95, ((reached + 1) / (PHASES.length + 1)) * 100) : 100
  const conflicts = result?.conflicts.length ?? 0
  const adopted = result?.evidence.length ?? 0
  const blocked = blockedCount(events)
  return <section className={'reasoning' + (live ? ' is-live' : '')} aria-label={t('How the guide decided', '판단 과정')}>
    <div className="reasoning-head">
      <strong>{t('How it decided', '판단 과정')}</strong>
      <span className="reasoning-total" role={live ? 'timer' : undefined} aria-live="off">{formatSeconds(total)}</span>
    </div>
    {!live && <p className="reasoning-note">{t('Broker-recorded steps; each step lasts until the next one. Model calls are reported by the worker.', '브로커가 기록한 단계예요. 각 단계 시간은 다음 단계가 시작될 때까지이며, 모델 호출은 워커가 보고한 값이에요.')}</p>}
    {live && <div className="reasoning-bar" aria-hidden="true"><i style={{ width: progress + '%' }}/></div>}
    <ol className="reasoning-steps" ref={list}>
      {rows.map((row, index) => {
        // Live: a phase without events is only "done" once a later phase has events of its own (judge follows writing).
        const state = !live ? (row.events.length ? 'done' : 'skip') : index === reached ? 'now' : index < reached && (row.events.length || row.phase !== 'judge') ? 'done' : 'todo'
        const [en, ko] = PHASE_LABEL[row.phase]
        const status = state === 'done' ? t('done', '완료') : state === 'now' ? t('in progress', '진행 중') : state === 'skip' ? t('not used', '사용 안 함') : t('waiting', '대기')
        return <li key={row.phase} className={'reasoning-step ' + state + (row.blocked ? ' has-blocked' : '')} aria-current={state === 'now' ? 'step' : undefined}>
          <div className="reasoning-step-head"><span className="reasoning-dot"/><b>{t(en, ko)}</b><span className="visually-hidden">, {status}</span>{row.events.length > 0 && <span className="reasoning-ms">{formatSeconds(row.ms)}</span>}</div>
          {row.phase === 'judge' && result && !live && <p className="reasoning-judge">{t(`${adopted} source${adopted === 1 ? '' : 's'} kept`, `출처 ${adopted}곳 채택`)}{conflicts > 0 && <> · <em>{t(`${conflicts} conflict${conflicts > 1 ? 's' : ''} resolved`, `충돌 ${conflicts}건 해결`)}</em></>}{blocked > 0 && <> · <em className="bad">{t(`${blocked} blocked`, `차단 ${blocked}건`)}</em></>}</p>}
          {row.events.length > 0 && <ul>{row.events.map((event, i) => {
            const shield = SHIELD[event.kind]
            const label = review && event.name === 'observing' ? ['Reading the sources (worker-reported)', '자료 읽기 (워커 보고)'] as [string, string] : EVENT_LABEL[event.name] ?? [event.name, event.name]
            return <li key={i} className={event.ok ? '' : 'bad'}>
              {(shield || !event.ok) && <span className={'shield-tag' + (event.ok ? '' : ' bad')}>{event.ok ? <ShieldCheck size={10}/> : <ShieldX size={10}/>}{event.ok ? t(...shield!) : isBlocked(event) ? t('blocked', '차단') : t('failed', '실패')}</span>}
              <span>{t(...label)}</span>{detailText(event.detail, t) && <small>{detailText(event.detail, t)}</small>}
            </li>
          })}</ul>}
        </li>
      })}
    </ol>
  </section>
}
