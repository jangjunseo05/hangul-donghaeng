import type { SandboxEvidence } from './types'

/** One rule for badge and card: the stored boundary test passed every check it ran. */
export const sandboxPassed = (evidence: SandboxEvidence | null | undefined): boolean =>
  Boolean(evidence && evidence.boundary_verdict === 'PASS' && evidence.boundary_checks_total > 0 && evidence.boundary_checks_passed === evidence.boundary_checks_total)

/** Static deployment configuration from the README; the broker does not observe model calls. */
export const MODEL_LABEL = { short: 'Nemotron 12B VL', host: 'L40S', full: 'NVIDIA Nemotron Nano 12B v2 VL · vLLM · L40S' }
