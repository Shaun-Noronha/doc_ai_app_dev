export interface KpiData {
  total_emissions_tco2e: number;
  energy_kwh: number;
  water_m3: number;
  waste_diversion_rate: number;
  sparkline: { period: string; tco2e: number }[];
}

export interface ScopeEmission {
  scope: string;
  label: string;
  tco2e: number;
}

export interface SourceEmission {
  source: string;
  scope: number;
  tco2e: number;
}

export interface Recommendation {
  id: number;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  category: string;
  potential_saving_tco2e?: number | null;
}

export type NavSection = 'dashboard' | 'scope1' | 'scope2' | 'scope3' | 'water';

export interface DocumentSource {
  document_id: number;
  document_type: string;
  source_filename: string;
  created_at: string;
}

export interface WaterUsageMetrics {
  volume_m3: number;
  volume_gallons: number;
}

export interface DashboardMetrics {
  scope_1_tco2e: number;
  scope_2_tco2e: number;
  scope_3_tco2e: number;
  water_usage: WaterUsageMetrics;
}

/** Full dashboard payload from GET /api/dashboard */
export interface DashboardPayload {
  kpis: KpiData;
  metrics?: DashboardMetrics;
  emissions_by_scope: ScopeEmission[];
  emissions_by_source: SourceEmission[];
  documents?: DocumentSource[];
  recommendations: Recommendation[];
}
