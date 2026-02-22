import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { KpiData, ScopeEmission, SourceEmission, Recommendation, DashboardMetrics, DocumentSource } from '../types';

export interface DashboardState {
  kpis: KpiData | null;
  metrics: DashboardMetrics | null;
  documents: DocumentSource[];
  byScope: ScopeEmission[];
  bySource: SourceEmission[];
  recommendations: Recommendation[];
  loading: boolean;
  error: string | null;
  /** Rebuild snapshot then refetch (e.g. after 503). */
  retry: () => Promise<void>;
}

export function useDashboard(): DashboardState {
  const [state, setState] = useState<Omit<DashboardState, 'retry'>>({
    kpis: null,
    metrics: null,
    documents: [],
    byScope: [],
    bySource: [],
    recommendations: [],
    loading: true,
    error: null,
  });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const payload = await api.dashboard();
      setState({
        kpis: payload.kpis,
        metrics: payload.metrics ?? null,
        documents: payload.documents ?? [],
        byScope: payload.emissions_by_scope,
        bySource: payload.emissions_by_source,
        recommendations: payload.recommendations,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: (err as Error).message ?? 'Failed to load dashboard data.',
      }));
    }
  }, []);

  const retry = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      await api.refresh();
      const payload = await api.dashboard();
      setState({
        kpis: payload.kpis,
        metrics: payload.metrics ?? null,
        documents: payload.documents ?? [],
        byScope: payload.emissions_by_scope,
        bySource: payload.emissions_by_source,
        recommendations: payload.recommendations,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: (err as Error).message ?? 'Refresh failed.',
      }));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, retry };
}
