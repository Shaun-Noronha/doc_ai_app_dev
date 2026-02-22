import {
  LayoutDashboard,
  Flame,
  Zap,
  PackageSearch,
  Droplets,
  Leaf,
} from 'lucide-react';
import type { NavSection } from '../types';

interface Props {
  active: NavSection;
  onNav: (s: NavSection) => void;
}

const items: { id: NavSection; icon: React.ReactNode; label: string }[] = [
  { id: 'dashboard', icon: <LayoutDashboard size={20} />, label: 'Dashboard' },
  { id: 'scope1', icon: <Flame size={20} />, label: 'Scope 1 – Fuel' },
  { id: 'scope2', icon: <Zap size={20} />, label: 'Scope 2 – Electricity' },
  { id: 'scope3', icon: <PackageSearch size={20} />, label: 'Scope 3 – Waste / Shipping' },
  { id: 'water', icon: <Droplets size={20} />, label: 'Water Usage' },
];

export default function Sidebar({ active, onNav }: Props) {
  return (
    <aside
      style={{ background: 'var(--color-sidebar)' }}
      className="fixed inset-y-0 left-0 w-[72px] hover:w-60 overflow-hidden transition-all duration-300 z-50 flex flex-col gap-1 pt-6 pb-8 group"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 mb-8">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'var(--color-emerald)' }}>
          <Leaf size={18} color="white" />
        </div>
        <span className="text-white font-semibold text-sm whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          Sustainability<br />
          <span className="text-emerald-400 font-bold">Pulse</span>
        </span>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col gap-1 px-2">
        {items.map((item) => {
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              onClick={() => onNav(item.id)}
              className={`flex items-center gap-3 px-3 py-3 rounded-xl text-left w-full transition-all duration-150 group/item
                ${isActive
                  ? 'bg-emerald-600/20 text-emerald-400'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
            >
              <span className={`shrink-0 ${isActive ? 'text-emerald-400' : ''}`}>
                {item.icon}
              </span>
              <span className="text-sm font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                {item.label}
              </span>
              {isActive && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 opacity-0 group-hover:opacity-100" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom spacer */}
      <div className="mt-auto px-4 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <p className="text-slate-600 text-[11px]">SME Sustainability Pulse</p>
        <p className="text-slate-700 text-[10px] mt-0.5">v1.0.0</p>
      </div>
    </aside>
  );
}
