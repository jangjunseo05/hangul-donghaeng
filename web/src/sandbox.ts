import type { SandboxEvidence, WorkerModel } from './types'

/** One rule for badge and card: the stored boundary test passed every check it ran. */
export const sandboxPassed = (evidence: SandboxEvidence | null | undefined): boolean =>
  Boolean(evidence && evidence.boundary_verdict === 'PASS' && evidence.boundary_checks_total > 0 && evidence.boundary_checks_passed === evidence.boundary_checks_total)

/** The model the connected worker says it is configured to call (self-reported, not proof of which model answered). */
export function workerModelLabel(model: WorkerModel | null | undefined) {
  if (!model?.id) return null
  const short = model.id.split('/').filter(Boolean).pop() || model.id
  return { id: model.id, short, thinkingOff: model.thinking === 'disabled' }
}
