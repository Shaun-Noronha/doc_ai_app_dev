import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { ScopePayload } from '../types';

export function useScope(scope: 1 | 2 | 3) {
  const [data, setData] = useState<ScopePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.scopePayload(scope);
      setData(payload);
    } catch (err) {
      setError((err as Error).message ?? 'Failed to load scope data');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    scopeTotal: data?.scopeTotal ?? 0,
    bySource: data?.bySource ?? [],
    sparkline: data?.sparkline ?? [],
    documents: data?.documents ?? [],
    loading,
    error,
  };
}
