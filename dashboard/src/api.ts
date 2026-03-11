import type {
  DashboardPayload,
  KpiData,
  ScopeEmission,
  SourceEmission,
  Recommendation,
  DocumentSource,
  ScopePayload,
  WaterPayload,
  UploadResult,
  ConfirmPayload,
  Vendor,
} from './types';

const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000';

const BASE = `${API_BASE}/api`;

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const msg =
      res.status === 503
        ? 'Dashboard not yet built. Run refresh or ingest documents first.'
        : `API error ${res.status}: ${path}`;
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  dashboard: () => get<DashboardPayload>('/dashboard'),

  refresh: async (): Promise<void> => {
    const res = await fetch(`${BASE}/refresh`, { method: 'POST' });
    if (!res.ok) throw new Error(`Refresh failed: ${res.status}`);
  },

  kpis: () => get<KpiData>('/kpis'),
  emissionsByScope: () => get<ScopeEmission[]>('/emissions-by-scope'),
  emissionsBySource: () => get<SourceEmission[]>('/emissions-by-source'),
  recommendations: () => get<Recommendation[]>('/recommendations'),

  documents: (scope?: number): Promise<DocumentSource[]> =>
    scope != null
      ? get<DocumentSource[]>(`/documents?scope=${scope}`)
      : get<DocumentSource[]>('/documents'),

  scopePayload: (scope: 1 | 2 | 3) => get<ScopePayload>(`/scope/${scope}`),

  waterPayload: () => get<WaterPayload>('/water'),

  vendors: () => get<Vendor[]>('/vendors'),
  vendorsSelected: () => get<string[]>('/vendors/selected'),

  setVendorsSelected: async (vendorIds: string[]): Promise<string[]> => {
    const res = await fetch(`${BASE}/vendors/selected`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vendor_ids: vendorIds }),
    });
    if (!res.ok) throw new Error(`Failed to save vendors: ${res.status}`);
    return res.json() as Promise<string[]>;
  },

  upload: async (file: File): Promise<UploadResult> => {
    const form = new FormData();
    form.append('file', file);

    const res = await fetch(`${BASE}/upload`, {
      method: 'POST',
      body: form,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `Upload failed: ${res.status}` }));
      throw new Error((err as { error?: string }).error ?? `Upload failed: ${res.status}`);
    }

    return res.json() as Promise<UploadResult>;
  },

  confirm: async (
    payload: ConfirmPayload
  ): Promise<{ ok: boolean; dashboard: DashboardPayload }> => {
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