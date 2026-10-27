import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FrameScheduler, GATE_SIZE, SceneGate, isSharpEnough, laplacianVariance, meanAbsDiff, nextObservationDelay, toGrey } from './autoCompanion'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('adaptive backoff (backend report §2-2 B)', () => {
  it('doubles the wait after consecutive quiet results, capped at 120 seconds', async () => {
    const observe = vi.fn(async () => 'quiet' as const)
    const scheduler = new FrameScheduler(observe)
    scheduler.setState(true, false)
    await vi.advanceTimersByTimeAsync(3000)
    expect(observe).toHaveBeenCalledTimes(1)
    for (const [wait, calls] of [[20000, 2], [40000, 3], [80000, 4], [120000, 5], [120000, 6]] as const) {
      await vi.advanceTimersByTimeAsync(wait - 1)
      expect(observe).toHaveBeenCalledTimes(calls - 1)
      await vi.advanceTimersByTimeAsync(1)
      expect(observe).toHaveBeenCalledTimes(calls)
    }
    scheduler.dispose()
  })
  it('a scene change resets the quiet backoff and allows a frame 8 seconds after the last answer', async () => {
    const observe = vi.fn(async () => 'quiet' as const)
    const scheduler = new FrameScheduler(observe)
    scheduler.setState(true, false)
    await vi.advanceTimersByTimeAsync(3000 + 20000 + 40000)
    expect(observe).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(5000)
    scheduler.notifySceneChange()
    await vi.advanceTimersByTimeAsync(2999)
    expect(observe).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(1)
    expect(observe).toHaveBeenCalledTimes(4)
    // Backoff was reset: the next quiet wait is the first step again.
    await vi.advanceTimersByTimeAsync(20000)
    expect(observe).toHaveBeenCalledTimes(5)
    scheduler.dispose()
  })
  it('a skipped frame is re-checked after 1 second and does not consume the interval', async () => {
    const outcomes: ('skipped' | 'shown')[] = ['skipped', 'skipped', 'shown']
    const observe = vi.fn(async () => outcomes.shift() ?? 'shown')
    const scheduler = new FrameScheduler(observe)
    scheduler.setState(true, false)
    await vi.advanceTimersByTimeAsync(3000)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)
    expect(observe).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(19999)
    expect(observe).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(1)
    expect(observe).toHaveBeenCalledTimes(4)
    scheduler.dispose()
  })
  it('backs off on errors and stops only after 3 consecutive failures', async () => {
    const onError = vi.fn()
    const observe = vi.fn(async () => 'error' as const)
    const scheduler = new FrameScheduler(observe, onError)
    scheduler.setState(true, false)
    await vi.advanceTimersByTimeAsync(3000)
    await vi.advanceTimersByTimeAsync(19999)
    expect(observe).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(observe).toHaveBeenCalledTimes(2)
    expect(onError).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(40000)
    expect(observe).toHaveBeenCalledTimes(3)
    expect(onError).toHaveBeenCalledTimes(1)
    scheduler.dispose()
  })
  it('delay table', () => {
    expect(nextObservationDelay('shown', 0, 0)).toBe(20000)
    expect(nextObservationDelay('quiet', 1, 0)).toBe(20000)
    expect(nextObservationDelay('quiet', 3, 0)).toBe(80000)
    expect(nextObservationDelay('quiet', 9, 0)).toBe(120000)
    expect(nextObservationDelay('error', 0, 2)).toBe(40000)
    expect(nextObservationDelay('skipped', 0, 0)).toBe(1000)
  })
})

const flat = (value: number) => new Uint8Array(GATE_SIZE * GATE_SIZE).fill(value)
const checker = (a: number, b: number) => Uint8Array.from({ length: GATE_SIZE * GATE_SIZE }, (_, i) => ((i % GATE_SIZE) + Math.floor(i / GATE_SIZE)) % 2 ? a : b)
const smooth = () => Uint8Array.from({ length: GATE_SIZE * GATE_SIZE }, (_, i) => 60 + (i % GATE_SIZE) * 2)
describe('scene change gate (backend report §2-2 A)', () => {
  it('needs the view held still for 1.2 seconds before the first frame', () => {
    const gate = new SceneGate()
    expect(gate.sample(flat(100), 0).ready).toBe(false)
    expect(gate.sample(flat(101), 600).ready).toBe(false)
    expect(gate.sample(flat(100), 1200).ready).toBe(true)
  })
  it('does not resend an unchanged view, but sends a changed and steady one', () => {
    const gate = new SceneGate()
    gate.sample(flat(100), 0); gate.sample(flat(100), 1500)
    gate.markSent()
    expect(gate.sample(flat(104), 3000).ready).toBe(false)
    expect(gate.sample(flat(170), 4000)).toMatchObject({ changed: true, stable: false, ready: false })
    expect(gate.sample(flat(170), 5300).ready).toBe(true)
  })
  it('a moving camera (unsteady frames) never passes', () => {
    const gate = new SceneGate()
    let ready = false
    for (let time = 0; time < 5000; time += 500) ready ||= gate.sample(flat(time % 1000 ? 40 : 200), time).ready
    expect(ready).toBe(false)
  })
  it('rejects blurry textured frames; flat frames have no texture to judge', () => {
    expect(isSharpEnough(checker(20, 230))).toBe(true)
    expect(isSharpEnough(smooth())).toBe(false)
    expect(isSharpEnough(flat(128))).toBe(true)
    expect(laplacianVariance(flat(50))).toBe(0)
  })
  it('a send marked with an earlier snapshot keeps later changes pending', () => {
    const gate = new SceneGate()
    gate.sample(flat(100), 0); gate.sample(flat(100), 1500)
    const snapshot = gate.current()
    gate.sample(flat(190), 1600); gate.sample(flat(190), 3000)
    gate.markSent(snapshot)
    expect(gate.state(3000).ready).toBe(true)
  })
  it('converts RGBA to grey and measures differences', () => {
    expect([...toGrey(Uint8Array.from([255, 255, 255, 255, 0, 0, 0, 255]))]).toEqual([255, 0])
    expect(meanAbsDiff(flat(10), flat(30))).toBe(20)
  })
})
