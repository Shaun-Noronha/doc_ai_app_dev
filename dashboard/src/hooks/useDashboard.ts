import { useEffect, useState } from 'react';
import { api } from '../api';
import type { KpiData, ScopeEmission, SourceEmission, Recommendation } from '../types';

export interface DashboardState {
  kpis: KpiData | null;
  byScope: ScopeEmission[];
  bySource: SourceEmission[];
  recommendations: Recommendation[];
  loading: boolean;
  error: string | null;
}

export function useDashboard(): DashboardState {
  const [state, setState] = useState<DashboardState>({
    kpis: null,
    byScope: [],
    bySource: [],
    recommendations: [],
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [kpis, byScope, bySource, recommendations] = await Promise.all([
          api.kpis(),
          api.emissionsByScope(),
          api.emissionsBySource(),
          api.recommendations(),
        ]);
        if (!cancelled) {
          setState({ kpis, byScope, bySource, recommendations, loading: false, error: null });
        }
      } catch (err) {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            loading: false,
            error: (err as Error).message ?? 'Failed to load dashboard data.',
          }));
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  return state;
}
