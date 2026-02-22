import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { WaterPayload } from '../types';

export function useWater() {
  const [data, setData] = useState<WaterPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.waterPayload();
      setData(payload);
    } catch (err) {
      setError((err as Error).message ?? 'Failed to load water data');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return {
    water_usage: data?.water_usage ?? { volume_m3: 0, volume_gallons: 0 },
    sparkline: data?.sparkline ?? [],
    documents: data?.documents ?? [],
    loading,
    error,
  };
}
