import { useEffect, useRef, useState } from 'react'
import { CircleAlert, LoaderCircle, Play, ShieldCheck, ShieldOff, ShieldX } from 'lucide-react'
import { ApiError } from '../api'
import { isProbeResult, labApi, pollJob, probeVerdict, PROBE_IDS } from '../labApi'
import type { ProbeVerdict } from '../labApi'
import type { ProbeAttempt, ProbeJob, ProbeResult, TraceEvent } from '../types'
import type { Guide } from '../useGuide'
import { formatSeconds, totalMs } from '../trace'

type T = Guide['t']
const ATTEMPT_LABEL: Record<ProbeAttempt['id'], [string, string]> = {
  read_outside_allowlist: ['Read a file outside the allow-list', '허용 목록 밖 파일 읽기'],
  write_code_dir: ['Write into the code folder /app', '코드 폴더(/app)에 쓰기'],
  egress_unlisted_host: ['Connect to an unlisted host', '목록에 없는 외부 호스트 접속'],
  broker_unlisted_path: ['Call a broker route not in the policy', '정책에 없는 브로커 경로 호출'],
}
const VERDICT: Record<ProbeVerdict, { en: string; ko: string; subEn: string; subKo: string }> = {
  blocked: { en: 'OpenShell blocked all 4 attempts', ko: 'OpenShell이 4건 모두 차단했어요', subEn: 'The worker saw every action denied, and the broker received nothing on its canary route.', subKo: '워커는 모든 시도가 거부됐다고 보고했고, 브로커의 미끼(canary) 경로 수신도 0건이에요.' },
  not_sandboxed: { en: 'Not sandboxed: a forbidden action was allowed', ko: '샌드박스 미적용: 금지된 시도가 허용됐어요', subEn: 'At least one action the policy forbids went through, e.g. a worker running without OpenShell. Shown as-is.', subKo: '정책이 막아야 할 시도가 하나 이상 통과했어요. 예를 들어 OpenShell 없이 실행 중인 워커일 수 있어요. 그대로 보여 드려요.' },
  cannot_judge: { en: 'Cannot judge this run', ko: '이번 실행은 판정할 수 없어요', subEn: 'An attempt ended in an error or is missing, so blocked and not-blocked cannot be told apart.', subKo: '오류가 났거나 빠진 시도가 있어 차단 여부를 가를 수 없어요.' },
  mismatch: { en: 'Cannot judge · evidence mismatch', ko: '판정 불가 · 근거 불일치', subEn: 'The worker reported denials, but the broker received a request on its canary route.', subKo: '워커는 거부됐다고 보고했지만 브로커 미끼(canary) 경로에 요청이 도착했어요.' },
}

function describeError(error: unknown, t: T) {
  if (error instanceof ApiError) {
    if (error.code === 'JOB_BUSY') return t('A test is already running for this session.', '이 세션에서 이미 테스트가 진행 중이에요.')
    if (error.code === 'WORKER_UNAVAILABLE') return t('No worker picked up the test. Check that the worker is running.', '테스트를 받은 워커가 없어요. 워커가 실행 중인지 확인해 주세요.')
    if (error.code === 'TIMEOUT') return t('The test took too long. Please try again.', '테스트가 너무 오래 걸렸어요. 다시 시도해 주세요.')
    if (error.status === 404 || error.status === 405) return t('This server does not offer the live block test yet.', '이 서버는 아직 실시간 차단 테스트을 지원하지 않아요.')
    return t('The test could not finish', '테스트를 마치지 못했어요') + ` (${error.code}).`
  }
  return t('The test could not finish.', '테스트를 마치지 못했어요.')
}

function AttemptRow({ attempt, id, t }: { attempt: ProbeAttempt | undefined; id: ProbeAttempt['id']; t: T }) {
  const [en, ko] = ATTEMPT_LABEL[id]
  const observed = attempt?.observed
  const brokerSeen = id === 'broker_unlisted_path'
  return <li className={'probe-row ' + (observed ?? 'pending')}>
    <span className="probe-icon" aria-hidden="true">{observed === 'denied' ? <ShieldCheck size={15}/> : observed === 'allowed' ? <ShieldOff size={15}/> : observed === 'error' ? <CircleAlert size={15}/> : <LoaderCircle className="spin" size={15}/>}</span>
    <div className="probe-what"><strong>{t(en, ko)}</strong>
      <small>{t('Worker-reported', '워커 보고')}{brokerSeen ? t(` · broker observed: received ${attempt?.broker_received ?? '–'}`, ` · 브로커 직접 관측: 수신 ${attempt?.broker_received ?? '–'}회`) : ''}{attempt?.detail ? ' · ' + attempt.detail : ''}</small></div>
    <span className="probe-observed">{observed === 'denied' ? t('denied', '거부됨') : observed === 'allowed' ? t('allowed', '허용됨') : observed === 'error' ? t('error', '오류') : t('waiting', '대기')}</span>
  </li>
}

/** F3: on-demand probe that asks the worker to attempt four policy-forbidden actions; the broker counts canary hits itself. */
export function ProbeCard({ g }: { g: Guide }) {
  const { t, session, health, healthFailed } = g
  const worker = Boolean(!healthFailed && health?.worker_connected)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ProbeResult | null>(null)
  const [trace, setTrace] = useState<TraceEvent[]>([])
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  async function run() {
    if (!session || running) return
    controller.current?.abort()
    const next = new AbortController()
    controller.current = next
    setRunning(true); setError(''); setResult(null); setTrace([])
    try {
      const queued = await labApi.submitProbe(session, next.signal)
      const done = await pollJob<ProbeJob>('/api/sandbox-probe/', queued.request_id, next.signal, job => setTrace(job.trace ?? []), isProbeResult)
      setResult(done)
    } catch (value) {
      if (!next.signal.aborted) setError(describeError(value, t))
    } finally { if (controller.current === next) setRunning(false) }
  }
  const verdict = result ? probeVerdict(result, trace) : null
  const copy = verdict ? VERDICT[verdict] : null
  return <section className="probe-card" aria-label={t('Live block test', '실시간 차단 테스트')}>
    <div className="probe-head">
      <div><strong>{t('Live block test', '실시간 차단 테스트')}</strong><small>{t('Asks the worker to try 4 things the policy forbids, right now.', '정책이 금지한 4가지를 지금 워커에게 시도하게 해요.')}</small></div>
      <button type="button" className="button button-primary probe-run" disabled={!session || running || !worker} onClick={() => void run()}>{running ? <LoaderCircle className="spin" size={15}/> : <Play size={15}/>}{running ? t('Testing…', '테스트 중…') : result ? t('Run again', '다시 실행') : t('Run test', '테스트 실행')}</button>
    </div>
    {!worker && !running && <p className="probe-need">{t('Needs a running worker.', '실행 중인 워커가 필요해요.')}</p>}
    {copy && verdict && <div className={'probe-verdict ' + verdict} role="status">
      {verdict === 'blocked' ? <ShieldCheck size={22}/> : verdict === 'not_sandboxed' ? <ShieldOff size={22}/> : <ShieldX size={22}/>}
      <div><b>{t(copy.en, copy.ko)}</b><p>{t(copy.subEn, copy.subKo)}</p></div>
    </div>}
    {(running || result) && <ul className="probe-rows">{PROBE_IDS.map(id => <AttemptRow key={id} id={id} attempt={result?.attempts.find(item => item.id === id)} t={t}/>)}</ul>}
    {result && <small className="probe-meta">{t('Worker label', '워커 라벨')} <code>{result.run_context}</code> {t('(a label, not proof)', '(라벨일 뿐 증거 아님)')} · {totalMs(trace) > 0 ? formatSeconds(totalMs(trace)) + ' · ' : ''}{Number.isFinite(Date.parse(result.finished_at)) ? new Date(result.finished_at).toLocaleTimeString(g.language === 'ko' ? 'ko-KR' : 'en-US') : ''}</small>}
    {error && <p className="probe-error" role="alert"><CircleAlert size={14}/>{error}</p>}
  </section>
}
