import type { DashboardPayload, KpiData, ScopeEmission, SourceEmission, Recommendation, DocumentSource, ScopePayload, WaterPayload, UploadResult, ConfirmPayload } from './types';

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

  /** Documents that contributed data; optional scope 0 (water), 1, 2, or 3 for scope-specific sources. */
  documents: (scope?: number): Promise<DocumentSource[]> =>
    scope != null ? get<DocumentSource[]>(`/documents?scope=${scope}`) : get<DocumentSource[]>('/documents'),

  /** Lightweight payload for Scope 1, 2, or 3 view (scopeTotal, bySource, sparkline, documents). */
  scopePayload: (scope: 1 | 2 | 3) => get<ScopePayload>(`/scope/${scope}`),

  /** Lightweight payload for Water view (water_usage, sparkline, documents). */
  waterPayload: () => get<WaterPayload>('/water'),

  /** Upload a document file to Doc AI + Gemini extraction. */
  upload: async (file: File): Promise<UploadResult> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `Upload failed: ${res.status}` }));
      throw new Error((err as { error?: string }).error ?? `Upload failed: ${res.status}`);
    }
    return res.json() as Promise<UploadResult>;
  },

  /** Confirm extracted fields, save to DB, return updated dashboard payload. */
  confirm: async (payload: ConfirmPayload): Promise<{ ok: boolean; dashboard: DashboardPayload }> => {
    const res = await fetch(`${BASE}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `Confirm failed: ${res.status}` }));
      throw new Error((err as { error?: string }).error ?? `Confirm failed: ${res.status}`);
    }
    return res.json() as Promise<{ ok: boolean; dashboard: DashboardPayload }>;
  },
};
