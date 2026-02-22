import type { KpiData, ScopeEmission, SourceEmission, Recommendation } from './types';

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  kpis: () => get<KpiData>('/kpis'),
  emissionsByScope: () => get<ScopeEmission[]>('/emissions-by-scope'),
  emissionsBySource: () => get<SourceEmission[]>('/emissions-by-source'),
  recommendations: () => get<Recommendation[]>('/recommendations'),
};
