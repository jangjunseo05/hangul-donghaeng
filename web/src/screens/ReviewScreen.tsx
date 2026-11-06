import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, CircleAlert, Download, FileCheck2, FileText, FileX2, LoaderCircle, Play, Quote, Scale, ShieldAlert } from 'lucide-react'
import { ApiError } from '../api'
import { isReviewResult, labApi, pollJob } from '../labApi'
import type { ReviewExclusion, ReviewInputs, ReviewJob, ReviewResult, ReviewSource, TraceEvent } from '../types'
import type { Guide } from '../useGuide'
import { ReasoningTimeline } from '../components/Timeline'

type T = Guide['t']
const REASON: Record<ReviewExclusion, [string, string, string, string]> = {
  irrelevant: ['Irrelevant', '무관함', 'No question or condition term appears in it (rule, checked by the broker).', '질문·조건 단어가 하나도 없어요 (규칙 · 브로커 검사).'],
  not_selected: ['Not selected', '선택 안 됨', 'Relevant, but outside the excerpt budget.', '관련은 있지만 발췌 한도 밖이에요.'],
  outdated: ['Outdated', '오래됨', 'A newer source supersedes it (model judgement, quotes checked by the broker).', '더 새로운 자료가 대체해요 (모델 판단 · 인용은 브로커 검사).'],
  conflict_superseded: ['Lost a conflict', '충돌로 제외', 'It conflicts with a stronger source (model judgement, quotes checked by the broker).', '더 믿을 만한 자료와 충돌해요 (모델 판단 · 인용은 브로커 검사).'],
  untrusted_instruction: ['Embedded instructions', '지시문 삽입', 'It tries to give the agent orders. Excluded and never sent to the model (rule, checked by the broker).', '에이전트에게 명령하려는 문장이 있어요. 제외했고 모델에 보내지 않았어요 (규칙 · 브로커 검사).'],
  unreadable: ['Unreadable', '읽을 수 없음', 'The file could not be read.', '파일을 읽을 수 없었어요.'],
}
const fileName = (path: string) => path.split(/[\\/]/).pop() || path
const DEFAULT_QUESTION: [string, string] = ['When is Haeon Palace open, and what should a visitor know before going?', '해온궁은 언제 열고, 방문 전에 무엇을 알아야 하나요?']

function describeError(error: unknown, t: T) {
  if (error instanceof ApiError) {
    if (error.code === 'WORKER_UNAVAILABLE') return t('No worker picked up the review. Check that the worker is running.', '자료 검토를 받은 워커가 없어요. 워커가 실행 중인지 확인해 주세요.')
    if (error.code === 'SUPERSEDED') return t('A newer request replaced this one.', '새 요청으로 바뀌었어요.')
    if (error.code === 'TIMEOUT') return t('The review took too long. Please try again.', '자료 검토가 너무 오래 걸렸어요. 다시 시도해 주세요.')
    if (error.status === 404 || error.status === 405) return t('This server does not offer source review yet.', '이 서버는 아직 자료 검토 모드를 지원하지 않아요.')
    return t('The review could not finish', '자료 검토를 마치지 못했어요') + ` (${error.code}).`
  }
  return t('The review could not finish.', '자료 검토를 마치지 못했어요.')
}

function SourceVerdict({ source, cited, t }: { source: ReviewSource; cited: boolean; t: T }) {
  const used = source.verdict === 'used'
  const reason = source.reason ? REASON[source.reason] : null
  return <li className={'review-source ' + (used ? 'used' : 'excluded') + (source.reason === 'untrusted_instruction' ? ' danger' : '')}>
    <span className="review-source-icon" aria-hidden="true">{used ? <FileCheck2 size={17}/> : source.reason === 'untrusted_instruction' ? <ShieldAlert size={17}/> : <FileX2 size={17}/>}</span>
    <div>
      <div className="review-source-head"><strong>{fileName(source.path)}</strong><span className={'review-verdict ' + (used ? 'used' : 'excluded')}>{used ? (cited ? t('Given to the model', '모델에 제공') : t('Given to the model · not cited', '모델에 제공 · 인용되지 않음')) : t('Excluded', '제외')}{reason ? ' · ' + t(reason[0], reason[1]) : ''}</span>{cited && <span className="review-cited">{t('cited', '인용됨')}</span>}</div>
      {reason && <p>{t(reason[2], reason[3])}</p>}
      {source.note && <p className="review-note"><b>{t("Model's reason · not an official verdict: ", '모델 판단 이유 · 공식 판정 아님: ')}</b>{source.note}</p>}
      <small>{source.as_of ? t('Dated ', '작성일 ') + source.as_of : t('No date', '날짜 없음')} · sha256 {source.sha256.slice(0, 10)}</small>
    </div>
  </li>
}

function ResultView({ result, sourceName, t }: { result: ReviewResult; sourceName(id: string): string; t: T }) {
  const cited = new Set(result.claims.flatMap(claim => claim.source_ids))
  const used = result.sources.filter(source => source.verdict === 'used').length
  return <div className="review-result">
    <div className={'review-status ' + result.status}>{result.status === 'answered' ? <FileCheck2 size={18}/> : <CircleAlert size={18}/>}
      <div><b>{result.status === 'answered' ? t('Answered from the sources it kept', '남긴 자료로 답했어요') : t('Not enough evidence to answer', '답하기에 근거가 부족해요')}</b>
        <small>{t(`${used} given to the model · ${result.sources.length - used} excluded · ${cited.size} cited`, `모델 제공 ${used} · 제외 ${result.sources.length - used} · 인용 ${cited.size}`)}{result.condition ? t(' · with your extra condition', ' · 추가 조건 반영') : ''}</small></div>
      {!result.verified_input && <span className="review-unverified">{t('Input not verified by the broker', '브로커 미검증 입력')}</span>}
    </div>
    {result.claims.length > 0 && <section className="review-block"><h3>{t('Answer', '답변')}</h3>{result.claims.map((claim, index) => <div className="review-claim" key={index}>
      <p>{claim.text}</p>
      {claim.quotes.map((quote, i) => <blockquote key={i}><Quote size={12}/><mark>{quote.text}</mark><cite>{sourceName(quote.source_id)}</cite></blockquote>)}
    </div>)}</section>}
    {result.conflicts.length > 0 && <section className="review-block"><h3><Scale size={15}/>{t('Conflicts resolved', '해결한 충돌')}</h3>{result.conflicts.map((conflict, index) => <div className="review-conflict" key={index}>
      <div className="conflict-vs">{conflict.source_ids.map((id, i) => <span key={id}>{i > 0 && <i>vs</i>}{sourceName(id)}</span>)}</div>
      {conflict.quotes.map((quote, i) => <blockquote key={i}><mark>{quote.text}</mark><cite>{sourceName(quote.source_id)}</cite></blockquote>)}
      <p><b>{t('Resolution: ', '판정: ')}</b>{conflict.resolution}</p>
      <small>{t('Why: ', '이유: ')}{conflict.reason}</small>
    </div>)}</section>}
    <section className="review-block"><h3>{t('Each source', '자료별 판정')}</h3><ul className="review-sources">{result.sources.map(source => <SourceVerdict key={source.id} source={source} cited={cited.has(source.id)} t={t}/>)}</ul></section>
    {result.unknowns.length > 0 && <section className="review-block unknowns"><h3>{t('Still unknown', '아직 모르는 점')}</h3><ul>{result.unknowns.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}
  </div>
}

/**
 * F2 source review: the sandboxed worker judges a mixed input set (relevant, outdated, conflicting,
 * irrelevant, injected instructions) and answers with checked quotes; the broker re-checks the verdicts.
 */
export default function ReviewScreen({ g, onClose }: { g: Guide; onClose(): void }) {
  const { t, session, language } = g
  const [inputs, setInputs] = useState<ReviewInputs | null>(null)
  const [inputsError, setInputsError] = useState(false)
  const [question, setQuestion] = useState(() => t(...DEFAULT_QUESTION))
  const [condition, setCondition] = useState('')
  const [running, setRunning] = useState(false)
  const [trace, setTrace] = useState<{ events: TraceEvent[]; startedAt: number }>({ events: [], startedAt: 0 })
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  const back = useRef<HTMLButtonElement>(null)
  useEffect(() => { back.current?.focus(); return () => controller.current?.abort() }, [])
  // L10: the suggested question follows the language until the user edits it.
  useEffect(() => { setQuestion(value => DEFAULT_QUESTION.includes(value) ? t(...DEFAULT_QUESTION) : value) }, [language])
  // The listing needs the session cookie, so wait for the session (opening #review directly races it).
  useEffect(() => {
    if (!session) return
    const load = new AbortController()
    setInputsError(false)
    labApi.reviewInputs(load.signal).then(setInputs, () => { if (!load.signal.aborted) setInputsError(true) })
    return () => load.abort()
  }, [session])
  async function run() {
    const text = question.trim()
    if (!session || !text || running) return
    controller.current?.abort()
    const next = new AbortController()
    controller.current = next
    const startedAt = Date.now()
    setRunning(true); setError(''); setResult(null); setRequestId(null); setTrace({ events: [], startedAt })
    try {
      const queued = await labApi.submitReview({ session_id: session, question: text.slice(0, 500), condition: condition.trim() ? condition.trim().slice(0, 300) : null, response_language: language }, next.signal)
      setRequestId(queued.request_id)
      const done = await pollJob<ReviewJob>('/api/reviews/', queued.request_id, next.signal, job => setTrace({ events: job.trace ?? [], startedAt }), isReviewResult, 120000)
      setResult(done)
    } catch (value) {
      if (!next.signal.aborted) setError(describeError(value, t))
    } finally { if (controller.current === next) setRunning(false) }
  }
  // The result's own source list wins when the worker read a different input set (contract).
  const listed = result && result.input_label !== inputs?.input_label ? result.sources : inputs?.sources ?? []
  const label = result?.input_label ?? inputs?.input_label
  const sourceName = (id: string) => fileName((result?.sources ?? inputs?.sources ?? []).find(source => source.id === id)?.path ?? id)
  return <section className="review-screen" aria-label={t('Source review mode', '자료 검토 모드')}>
    <header className="review-top">
      <button type="button" ref={back} className="icon-button" onClick={onClose} aria-label={t('Back', '뒤로')}><ArrowLeft size={18}/></button>
      <div><h2>{t('Source review mode', '자료 검토 모드')}</h2><small>{t('Which sources does the agent trust, and why?', '에이전트는 어떤 자료를 믿고, 왜 그런가요?')}</small></div>
    </header>
    <div className="review-body">
      {label === 'review-demo' && <p className="practice-banner review-banner"><FileText size={15}/><span>{t('Fictional practice material · “Haeon Palace” is not a real place. It mixes a current notice, an old blog, an unrelated list and a post with injected instructions.', '가상 연습 자료 · “해온궁”은 실제 장소가 아니에요. 최신 공지, 오래된 블로그, 무관한 목록, 지시문이 숨은 게시글이 섞여 있어요.')}</span></p>}
      <section className="review-block"><h3>{t('Input documents', '입력 문서')}{label && <code>{label}</code>}</h3>
        {inputsError && !result && <p className="review-muted">{t('The input list is not available from this server.', '이 서버에서 입력 목록을 받을 수 없어요.')}</p>}
        <ul className="review-inputs">{listed.map(source => <li key={source.id}><FileText size={14}/><span>{fileName(source.path)}</span><small>{source.as_of ?? t('no date', '날짜 없음')}{'bytes' in source ? ` · ${(source as { bytes: number }).bytes} B` : ''}</small></li>)}</ul>
      </section>
      <section className="review-block review-form">
        <label htmlFor="review-question">{t('Question', '질문')}</label>
        <textarea id="review-question" value={question} maxLength={500} rows={2} onChange={event => setQuestion(event.target.value)}/>
        <label htmlFor="review-condition">{t('Extra condition (optional)', '추가 조건 (선택)')}</label>
        <input id="review-condition" value={condition} maxLength={300} placeholder={t('e.g. I am visiting on a Monday with a wheelchair user', '예: 월요일에 휠체어 이용자와 함께 방문해요')} onChange={event => setCondition(event.target.value)}/>
        <button type="button" className="button button-primary review-run" disabled={!session || running || !question.trim()} onClick={() => void run()}>{running ? <LoaderCircle className="spin" size={16}/> : <Play size={16}/>}{running ? t('Reviewing in the sandbox…', '샌드박스에서 검토 중…') : t('Review the sources', '자료 검토하기')}</button>
      </section>
      {(running || trace.events.length > 0) && <ReasoningTimeline review live={running} follow={running} events={trace.events} startedAt={trace.startedAt} totalMs={trace.events.length ? undefined : 0} t={t}/>}
      {error && <div className="error-panel" role="alert"><CircleAlert size={18}/><div><strong>{t('Let’s try that again.', '다시 한번 해볼까요?')}</strong><p>{error}</p></div></div>}
      {result && <ResultView result={result} sourceName={sourceName} t={t}/>}
      {result && requestId && /^[\w-]+$/.test(requestId) && <div className="download-row"><span><Download size={15}/>{t('Broker-saved answer', '브로커가 저장한 답변')}</span><div>{['json', 'md'].map(format => <a className="download-link" key={format} href={`/api/reviews/${encodeURIComponent(requestId)}/download?format=${format}`} download><Download size={14}/>{format.toUpperCase()}</a>)}</div></div>}
    </div>
  </section>
}
