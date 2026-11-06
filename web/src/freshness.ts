/** Source freshness relative to when the answer was made. as_of may be a year, year-month or full date. */
export type Freshness = { level: 'fresh' | 'aging' | 'stale' | 'unknown'; months: number | null }
export function freshness(asOf: string | null, reference: string): Freshness {
  const match = asOf?.trim().match(/^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/)
  const ref = Date.parse(reference)
  if (!match || !Number.isFinite(ref)) return { level: 'unknown', months: null }
  const then = Date.UTC(Number(match[1]), match[2] ? Number(match[2]) - 1 : 0, match[3] ? Number(match[3]) : 1)
  const months = Math.max(0, Math.floor((ref - then) / (30.44 * 24 * 3600 * 1000)))
  return { level: months <= 6 ? 'fresh' : months <= 24 ? 'aging' : 'stale', months }
}
