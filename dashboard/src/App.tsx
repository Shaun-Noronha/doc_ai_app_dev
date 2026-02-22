import { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './views/Dashboard';
import type { NavSection } from './types';

const PLACEHOLDER_SECTIONS: Partial<Record<NavSection, string>> = {
  scope1: 'Scope 1 – Stationary & Vehicle Fuel',
  scope2: 'Scope 2 – Purchased Electricity',
  scope3: 'Scope 3 – Waste & Shipping',
  water: 'Water Usage',
};

export default function App() {
  const [active, setActive] = useState<NavSection>('dashboard');

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--color-bg)' }}>
      <Sidebar active={active} onNav={setActive} />

      {/* Main area – offset for slim sidebar (72px) */}
      <div className="flex-1 ml-[72px] min-h-screen">
        {active === 'dashboard' ? (
          <Dashboard />
        ) : (
          <div className="flex items-center justify-center min-h-screen">
            <div className="text-center p-12 rounded-2xl"
              style={{
                background: 'var(--color-card)',
                backdropFilter: 'blur(16px)',
                border: '1px solid rgba(255,255,255,0.9)',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <div className="w-16 h-16 rounded-2xl bg-emerald-100 flex items-center justify-center mx-auto mb-4">
                <span className="text-3xl">🌱</span>
              </div>
              <h2 className="text-xl font-bold text-slate-800 mb-2">
                {PLACEHOLDER_SECTIONS[active]}
              </h2>
              <p className="text-sm text-slate-400 max-w-xs">
                Detailed drilldown views coming soon. Return to the main dashboard for aggregated metrics.
              </p>
              <button
                onClick={() => setActive('dashboard')}
                className="mt-6 px-5 py-2.5 text-sm font-semibold text-white rounded-xl transition-all duration-150 hover:opacity-90 active:scale-95"
                style={{ background: 'var(--color-emerald)' }}
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
