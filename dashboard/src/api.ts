import type { DashboardPayload, KpiData, ScopeEmission, SourceEmission, Recommendation } from './types';

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const msg = res.status === 503
      ? 'Dashboard not yet built. Run refresh or ingest documents first.'
      : `API error ${res.status}: ${path}`;
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  /** Single request: full dashboard from cached snapshot (fast). */
  dashboard: () => get<DashboardPayload>('/dashboard'),
  refresh: async (): Promise<void> => {
    const res = await fetch(`${BASE}/refresh`, { method: 'POST' });
    if (!res.ok) throw new Error(`Refresh failed: ${res.status}`);
  },
  kpis: () => get<KpiData>('/kpis'),
  emissionsByScope: () => get<ScopeEmission[]>('/emissions-by-scope'),
  emissionsBySource: () => get<SourceEmission[]>('/emissions-by-source'),
  recommendations: () => get<Recommendation[]>('/recommendations'),
};
