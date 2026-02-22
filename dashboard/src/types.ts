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

/** A single field returned by /api/upload for human review */
export interface ReviewField {
  key: string;
  label: string;
  value: string | number | null;
  editable: boolean;
}

/** Response from POST /api/upload */
export interface UploadResult {
  doc_type: string;
  fields: ReviewField[];
  warnings: string[];
}

/** Body sent to POST /api/confirm */
export interface ConfirmPayload {
  doc_type: string;
  fields: Record<string, string>;
  filename: string;
}

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

/** Sparkline point (monthly tCO₂e) */
export interface SparklinePoint {
  period: string;
  tco2e: number;
}

/** Lightweight payload from GET /api/scope/1|2|3 */
export interface ScopePayload {
  scopeTotal: number;
  bySource: SourceEmission[];
  sparkline: SparklinePoint[];
  documents: DocumentSource[];
}

/** Lightweight payload from GET /api/water */
export interface WaterPayload {
  water_usage: WaterUsageMetrics;
  sparkline: SparklinePoint[];
  documents: DocumentSource[];
}

export interface Vendor {
  vendor_id: string;
  vendor_name: string;
  category: string;
  product_or_service: string;
  carbon_intensity: number;
  sustainability_score: number;
  distance_km_from_sme: number | null;
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
