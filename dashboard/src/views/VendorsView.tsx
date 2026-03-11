import { useCallback, useEffect, useState } from 'react';
import { Store } from 'lucide-react';
import SectionLayout from './SectionLayout';
import { api } from '../api';
import type { Vendor } from '../types';

export default function VendorsView() {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [vendorList, ids] = await Promise.all([
        api.vendors(),
        api.vendorsSelected(),
      ]);
      setVendors(vendorList);
      setSelectedIds(new Set(ids));
    } catch (err) {
      setError((err as Error).message ?? 'Failed to load vendors');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = (vendorId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(vendorId)) next.delete(vendorId);
      else next.add(vendorId);
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.setVendorsSelected(Array.from(selectedIds));
      setSelectedIds(new Set(updated));
    } catch (err) {
      setError((err as Error).message ?? 'Failed to save selection');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionLayout
      title="Vendors"
      subtitle="Select vendors for recommendations"
      icon={<Store size={20} color="white" />}
    >
      {error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{ background: 'rgba(244,63,94,0.1)', color: 'var(--color-text)', border: '1px solid rgba(244,63,94,0.3)' }}
        >
          {error}
        </div>
      )}

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <p className="text-sm opacity-80" style={{ color: 'var(--color-text)' }}>
          {vendors.length} vendor{vendors.length !== 1 ? 's' : ''} · {selectedIds.size} selected
        </p>
        <button
          type="button"
          onClick={save}
          disabled={loading || saving}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white transition-opacity disabled:opacity-50"
          style={{ background: 'var(--chart-primary)' }}
        >
          {saving ? 'Saving…' : 'Save selection'}
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-24 rounded-xl animate-pulse"
              style={{ background: 'var(--color-card-outline)' }}
            />
          ))}
        </div>
      ) : (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {vendors.map((v) => (
            <li
              key={v.vendor_id}
              className="flex items-center gap-4 rounded-2xl p-4 border cursor-pointer transition-colors"
              style={{
                borderColor: 'var(--color-card-outline)',
                background: selectedIds.has(v.vendor_id) ? 'rgba(5, 74, 41, 0.06)' : 'var(--color-card)',
                boxShadow: 'var(--shadow-card)',
              }}
              onClick={() => toggle(v.vendor_id)}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(v.vendor_id)}
                onChange={() => toggle(v.vendor_id)}
                className="w-5 h-5 rounded border-2 shrink-0"
                style={{ accentColor: 'var(--chart-primary)' }}
                onClick={(e) => e.stopPropagation()}
              />
              <div className="min-w-0 flex-1">
                <p className="font-semibold truncate" style={{ color: 'var(--color-text)' }}>{v.vendor_name}</p>
                <p className="text-xs opacity-70 truncate" style={{ color: 'var(--color-text)' }}>{v.category} · {v.product_or_service}</p>
                <p className="text-xs mt-0.5 opacity-60" style={{ color: 'var(--color-text)' }}>
                  Sustainability {v.sustainability_score} · {v.carbon_intensity} kg CO₂e/unit
                  {v.distance_km_from_sme != null ? ` · ${v.distance_km_from_sme} km` : ''}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {!loading && vendors.length === 0 && (
        <p className="text-sm opacity-70" style={{ color: 'var(--color-text)' }}>
          No vendors in the database. Run the vendor seed script to load sample data.
        </p>
      )}
    </SectionLayout>
  );
}
