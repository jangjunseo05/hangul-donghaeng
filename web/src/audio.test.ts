import { describe, expect, it, vi } from 'vitest'
import { FallbackPlayer, TtsUnavailable, pickVoice, splitForSpeech } from './audio'
import type { AudioPlayer } from './audio'

const voice = (name: string, lang: string) => ({ name, lang, localService: true, default: false })
describe('female-first voice choice', () => {
  it('prefers known female voices and avoids known male voices', () => {
    const voices = [voice('Microsoft InJoon Online (Natural) - Korean', 'ko-KR'), voice('Microsoft SunHi Online (Natural) - Korean', 'ko-KR'), voice('Google US English Male', 'en-US'), voice('Samantha', 'en-US'), voice('Daniel', 'en-GB')]
    expect(pickVoice(voices, 'ko')?.name).toContain('SunHi')
    expect(pickVoice(voices, 'en')?.name).toBe('Samantha')
  })
  it('does not treat "female" as male and still returns a voice when no hint matches', () => {
    expect(pickVoice([voice('Generic Male', 'en-US'), voice('Generic Female', 'en-US')], 'en')?.name).toBe('Generic Female')
    expect(pickVoice([voice('Unknown', 'ko_KR')], 'ko')?.name).toBe('Unknown')
    expect(pickVoice([voice('Samantha', 'en-US')], 'ko')).toBeUndefined()
  })
})

const player = (impl: AudioPlayer['play']): AudioPlayer => ({ play: vi.fn(impl), stop: vi.fn() })
describe('server voice first, browser voice as fallback', () => {
  it('falls back when the server voice is unavailable (e.g. 503)', async () => {
    const server = player(async () => { throw new TtsUnavailable('SERVER_TTS_503') })
    const browser = player(async () => {})
    await new FallbackPlayer([server, browser]).play('안녕하세요', 'ko', new AbortController().signal)
    expect(server.play).toHaveBeenCalledTimes(1)
    expect(browser.play).toHaveBeenCalledWith('안녕하세요', 'ko', expect.anything())
  })
  it('uses only the server voice when it works', async () => {
    const server = player(async () => {})
    const browser = player(async () => {})
    await new FallbackPlayer([server, browser]).play('Hello', 'en', new AbortController().signal)
    expect(browser.play).not.toHaveBeenCalled()
  })
  it('a user stop is not treated as a failure to fall back from', async () => {
    const controller = new AbortController()
    const server = player(async () => { controller.abort(); throw new DOMException('Aborted', 'AbortError') })
    const browser = player(async () => {})
    await expect(new FallbackPlayer([server, browser]).play('Hello', 'en', controller.signal)).rejects.toThrow()
    expect(browser.play).not.toHaveBeenCalled()
  })
})

describe('sentence-sized speech chunks', () => {
  it('keeps short sentences together and splits at sentence ends', () => {
    expect(splitForSpeech('Hi. This is Gyeongbokgung.')).toEqual(['Hi. This is Gyeongbokgung.'])
    const long = 'Gyeongbokgung is a royal palace built in 1395 for Joseon, the kingdom that ruled Korea before modern times. It was the main palace — think of it as the headquarters where the king lived and ran the country. Walk in through the big front gate and notice how the halls line up.'
    const chunks = splitForSpeech(long)
    expect(chunks.length).toBeGreaterThan(1)
    expect(chunks.join(' ')).toBe(long)
    expect(chunks.every(chunk => chunk.length <= 220)).toBe(true)
  })
  it('splits Korean text and very long sentences without losing words', () => {
    expect(splitForSpeech('경복궁은 1395년에 지은 궁궐이에요. 조선의 중심 궁궐이었어요!', 40)).toEqual(['경복궁은 1395년에 지은 궁궐이에요.', '조선의 중심 궁궐이었어요!'])
    const words = Array.from({ length: 80 }, (_, i) => 'word' + i).join(' ')
    const chunks = splitForSpeech(words, 100)
    expect(chunks.join(' ')).toBe(words)
    expect(chunks.every(chunk => chunk.length <= 100)).toBe(true)
    expect(splitForSpeech('   ')).toEqual([])
  })
})
