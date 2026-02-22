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
