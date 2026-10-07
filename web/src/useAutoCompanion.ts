import { useEffect, useRef } from 'react'
import { FrameScheduler } from './autoCompanion'

export function useAutoCompanion(enabled: boolean, paused: boolean, observe: (current: () => boolean) => Promise<void>, onError: () => void) {
  const callback = useRef(observe)
  const errorCallback = useRef(onError)
  callback.current = observe
  errorCallback.current = onError
  const scheduler = useRef<FrameScheduler | null>(null)
  useEffect(() => {
    const instance = new FrameScheduler(current => callback.current(current), () => errorCallback.current())
    scheduler.current = instance
    return () => { instance.dispose(); scheduler.current = null }
  }, [])
  useEffect(() => { scheduler.current?.setState(enabled, paused) }, [enabled, paused])
  return { interrupt: () => scheduler.current?.interrupt() }
}
