import { useEffect, useState } from 'react'
import { ApiError } from '../api'
import type { Loaded } from '../tabsApi'

export type LoadState<T> = { status: 'loading' } | { status: 'error'; code: string } | { status: 'ready'; data: T; fixture: boolean }
/** Loads on mount and whenever `key` changes; stale responses are ignored. */
export function useLoaded<T>(key: string | null, load: (signal: AbortSignal) => Promise<Loaded<T>>): LoadState<T> {
  const [state, setState] = useState<LoadState<T>>({ status: 'loading' })
  useEffect(() => {
    if (key === null) return
    const controller = new AbortController()
    setState({ status: 'loading' })
    load(controller.signal).then(value => { if (!controller.signal.aborted) setState({ status: 'ready', ...value }) },
      error => { if (!controller.signal.aborted) setState({ status: 'error', code: error instanceof ApiError ? error.code : 'OFFLINE' }) })
    return () => controller.abort()
  }, [key])
  return state
}
