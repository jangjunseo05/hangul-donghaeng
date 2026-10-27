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

// Platform voice lists from research phase2 §M2-2 (Readium Speech DB). Names only; not real-device dumps.
const PLATFORMS: { platform: string; ko: [string, string][]; en: [string, string][]; female: { ko: string; en: string } }[] = [
  { platform: 'iOS / macOS', ko: [['Minsu', 'ko-KR'], ['Jian', 'ko-KR'], ['Yuna', 'ko-KR'], ['Suhyun', 'ko-KR']], en: [['Alex', 'en-US'], ['Aaron', 'en-US'], ['Evan', 'en-US'], ['Ava', 'en-US'], ['Nathan', 'en-US'], ['Samantha', 'en-US']], female: { ko: 'Yuna', en: 'Ava' } },
  { platform: 'Android Google TTS (names)', ko: [['Google 한국어 3 (Natural)', 'ko-KR'], ['Google 한국어 4 (Natural)', 'ko-KR'], ['Google 한국어 1 (Natural)', 'ko-KR'], ['Google 한국어 2 (Natural)', 'ko-KR']], en: [['Google US English 3 (Natural)', 'en-US'], ['Google US English 4 (Natural)', 'en-US'], ['Google US English 6 (Natural)', 'en-US'], ['Google US English 1 (Natural)', 'en-US'], ['Google US English 5 (Natural)', 'en-US']], female: { ko: 'Google 한국어 2 (Natural)', en: 'Google US English 5 (Natural)' } },
  { platform: 'Android Google TTS (voice ids)', ko: [['ko-kr-x-koc-local', 'ko_KR'], ['ko-kr-x-kod-network', 'ko_KR'], ['ko-kr-x-ism-local', 'ko_KR']], en: [['en-us-x-iom-local', 'en_US'], ['en-us-x-iol-network', 'en_US'], ['en-us-x-tpd-local', 'en_US'], ['en-us-x-iog-local', 'en_US']], female: { ko: 'ko-kr-x-ism-local', en: 'en-us-x-iog-local' } },
  { platform: 'Edge online', ko: [['Microsoft InJoon Online (Natural) - Korean (Korea)', 'ko-KR'], ['Microsoft Hyunsu Online (Natural) - Korean (Korea)', 'ko-KR'], ['Microsoft SunHi Online (Natural) - Korean (Korea)', 'ko-KR']], en: [['Microsoft Guy Online (Natural) - English (United States)', 'en-US'], ['Microsoft Jenny Online (Natural) - English (United States)', 'en-US']], female: { ko: 'Microsoft SunHi Online (Natural) - Korean (Korea)', en: 'Microsoft Jenny Online (Natural) - English (United States)' } },
  { platform: 'Windows / Chrome desktop', ko: [['Microsoft Heami - Korean (Korean)', 'ko-KR'], ['Google 한국의', 'ko-KR']], en: [['Microsoft David - English (United States)', 'en-US'], ['Microsoft Zira - English (United States)', 'en-US'], ['Google US English', 'en-US']], female: { ko: 'Google 한국의', en: 'Microsoft Zira - English (United States)' } },
]
describe('female voice ranks first on each platform (research §M2-2)', () => {
  for (const { platform, ko, en, female } of PLATFORMS) it(platform, () => {
    const voices = [...ko, ...en].map(([name, lang]) => voice(name, lang))
    expect(pickVoice(voices, 'ko')?.name).toBe(female.ko)
    expect(pickVoice(voices, 'en')?.name).toBe(female.en)
  })
  it('a male "Google US English 3/4/6" never beats the generic female "Google US English"', () => {
    expect(pickVoice([voice('Google US English 3 (Natural)', 'en-US'), voice('Google US English', 'en-US')], 'en')?.name).toBe('Google US English')
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
    // The first chunk is a single sentence so the first audio starts early; later short sentences merge.
    expect(splitForSpeech('Hi. This is Gyeongbokgung. It is big. Look up.')).toEqual(['Hi.', 'This is Gyeongbokgung. It is big. Look up.'])
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
