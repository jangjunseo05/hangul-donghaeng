import { describe, expect, it } from 'vitest'
import { chromeIntentUrl, detectInAppBrowser } from './inApp'

describe('in-app browser detection', () => {
  it('detects common in-app browsers with their platform', () => {
    expect(detectInAppBrowser('Mozilla/5.0 (Linux; Android 14; SM-S921N; wv) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36 KAKAOTALK 10.8.0')).toEqual({ name: 'KakaoTalk', platform: 'android' })
    expect(detectInAppBrowser('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Instagram 350.0')).toEqual({ name: 'Instagram', platform: 'ios' })
    expect(detectInAppBrowser('Mozilla/5.0 (Linux; Android 14; Pixel 8; wv) AppleWebKit/537.36 Version/4.0 Chrome/129.0 Mobile Safari/537.36')?.name).toBe('Android WebView')
  })
  it('does not flag regular Chrome or Safari', () => {
    expect(detectInAppBrowser('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36')).toBeNull()
    expect(detectInAppBrowser('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1')).toBeNull()
  })
  it('builds a Chrome intent link for the same page', () => {
    expect(chromeIntentUrl('https://guide.example/look?x=1')).toBe('intent://guide.example/look?x=1#Intent;scheme=https;package=com.android.chrome;end')
  })
})
