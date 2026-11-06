import { useEffect, useState } from 'react'
import { useGuide } from './useGuide'
import type { Tab } from './contract'
import { TabBar, TopBar } from './components/shell'
import { StatusDialog } from './components/StatusDialog'
import LookScreen from './screens/LookScreen'
import { EatScreen, LandmarksScreen } from './screens/places'
import RoutesScreen from './screens/RoutesScreen'
import ReviewScreen from './screens/ReviewScreen'

/** App shell: top bar, one screen per tab, bottom tab bar with the Look camera in the middle. */
export default function App() {
  const g = useGuide()
  const [tab, setTab] = useState<Tab>('look')
  // F2 source review is an overlay; #review opens it directly (demo shortcut).
  const [review, setReview] = useState(() => location.hash === '#review')
  // Entering review (button or #review) stops the camera and automatic companion so nothing supersedes the review job.
  useEffect(() => { if (review) { g.prioritizeUser(); g.stopAutomatic(); g.camera.stop(); g.speech.stopReading() } }, [review])
  useEffect(() => {
    const sync = () => setReview(location.hash === '#review')
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  function openReview(next: boolean) {
    history.replaceState(null, '', next ? '#review' : location.pathname + location.search)
    setReview(next)
  }
  function changeTab(next: Tab) {
    if (review) openReview(false)
    if (next === tab) return
    // Leaving Look turns the camera and automatic companion off; nothing is captured in the background.
    if (tab === 'look' && next !== 'look') { g.stopAutomatic(); g.camera.stop() }
    g.speech.stopReading()
    setTab(next)
  }
  return <div className="app-shell">
    <TopBar g={g}/>
    <main className="app-main">
      <LookScreen g={g} hidden={tab !== 'look' || review}/>
      {!review && tab === 'landmarks' && <LandmarksScreen g={g} onTab={changeTab}/>}
      {!review && tab === 'eat' && <EatScreen g={g} onTab={changeTab}/>}
      {!review && tab === 'routes' && <RoutesScreen g={g}/>}
      {review && <ReviewScreen g={g} onClose={() => openReview(false)}/>}
    </main>
    <TabBar tab={tab} onTab={changeTab} t={g.t}/>
    <StatusDialog g={g} onReview={() => openReview(true)}/>
  </div>
}
