import { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './views/Dashboard';
import Scope1View from './views/Scope1View';
import Scope2View from './views/Scope2View';
import Scope3View from './views/Scope3View';
import WaterView from './views/WaterView';
import type { NavSection } from './types';

export default function App() {
  const [active, setActive] = useState<NavSection>('dashboard');

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--color-bg)' }}>
      <Sidebar active={active} onNav={setActive} />

      <div className="flex-1 ml-[72px] min-h-screen">
        {active === 'dashboard' && <Dashboard />}
        {active === 'scope1' && <Scope1View />}
        {active === 'scope2' && <Scope2View />}
        {active === 'scope3' && <Scope3View />}
        {active === 'water' && <WaterView />}
      </div>
    </div>
  );
}
