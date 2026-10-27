export type InAppBrowser = { name: string; platform: 'android' | 'ios' | 'other' } | null

const IN_APP: [RegExp, string][] = [
  [/KAKAOTALK/i, 'KakaoTalk'],
  [/NAVER\(inapp|NAVER\/\d/i, 'NAVER'],
  [/Instagram/i, 'Instagram'],
  [/FBAN|FBAV|FB_IAB/i, 'Facebook'],
  [/\bLine\//i, 'LINE'],
  [/DaumApps/i, 'Daum'],
  [/everytimeApp/i, 'Everytime'],
  [/BAND\//i, 'BAND'],
  [/; wv\)/i, 'Android WebView'],
]
/** Detects in-app browsers that often block the camera or voice input. */
export function detectInAppBrowser(ua: string): InAppBrowser {
  const match = IN_APP.find(([pattern]) => pattern.test(ua))
  if (!match) return null
  const platform = /Android/i.test(ua) ? 'android' : /iPhone|iPad|iPod/i.test(ua) ? 'ios' : 'other'
  return { name: match[1], platform }
}
/** Android intent link that reopens the current https page in Chrome. */
export function chromeIntentUrl(href: string) {
  const url = new URL(href)
  return `intent://${url.host}${url.pathname}${url.search}#Intent;scheme=${url.protocol.replace(':', '')};package=com.android.chrome;end`
}
