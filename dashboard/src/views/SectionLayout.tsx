import type { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  icon: ReactNode;
  children: ReactNode;
}

export default function SectionLayout({ title, subtitle, icon, children }: Props) {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-bg)' }}>
      <header
        className="sticky top-0 z-40 flex items-center gap-4 px-8 py-4"
        style={{
          background: 'rgba(254,250,224,0.9)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid var(--color-card-outline)',
        }}
      >
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'var(--chart-primary)' }}
        >
          {icon}
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text)' }}>{title}</h1>
          {subtitle && <p className="text-xs mt-0.5 opacity-70" style={{ color: 'var(--color-text)' }}>{subtitle}</p>}
        </div>
      </header>
      <main className="flex-1 px-8 py-6 flex flex-col gap-6 max-w-[1600px] w-full mx-auto">
        {children}
      </main>
    </div>
  );
}
