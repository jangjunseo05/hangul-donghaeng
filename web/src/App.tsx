import { useState } from 'react'
import { useGuide } from './useGuide'
import type { Tab } from './contract'
import { TabBar, TopBar } from './components/shell'
import { StatusDialog } from './components/StatusDialog'
import LookScreen from './screens/LookScreen'
import { EatScreen, LandmarksScreen } from './screens/places'
import RoutesScreen from './screens/RoutesScreen'

/** App shell: top bar, one screen per tab, bottom tab bar with the Look camera in the middle. */
export default function App() {
  const g = useGuide()
  const [tab, setTab] = useState<Tab>('look')
  function changeTab(next: Tab) {
    if (next === tab) return
    // Leaving Look turns the camera and automatic companion off; nothing is captured in the background.
    if (tab === 'look' && next !== 'look') { g.stopAutomatic(); g.camera.stop() }
    g.speech.stopReading()
    setTab(next)
  }
  return <div className="app-shell">
    <TopBar g={g}/>
    <main className="app-main">
      <LookScreen g={g} hidden={tab !== 'look'}/>
      {tab === 'landmarks' && <LandmarksScreen g={g} onTab={changeTab}/>}
      {tab === 'eat' && <EatScreen g={g} onTab={changeTab}/>}
      {tab === 'routes' && <RoutesScreen g={g}/>}
    </main>
    <TabBar tab={tab} onTab={changeTab} t={g.t}/>
    <StatusDialog g={g}/>
  </div>
}
