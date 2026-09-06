/** Thin API client. The frontend never computes analysis - it renders what the backend produced. */

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      /* response was not JSON - keep the status text */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  assets: () => request<AssetCard[]>("/assets"),
  asset: (symbol: string, refresh = false) =>
    request<AssetDetail>(`/assets/${symbol}${refresh ? "?refresh=true" : ""}`),
  report: (symbol: string) => request<{ text: string; report_id: string }>(`/assets/${symbol}/report`),
  sources: (symbol: string) => request<SourcesResponse>(`/assets/${symbol}/sources`),
  global: () => request<GlobalMarket>("/global"),
  providers: () => request<ProvidersResponse>("/providers"),
  alerts: () => request<Alert[]>("/alerts"),
  evaluation: () => request<Evaluation>("/evaluation"),
  knowledgeStats: () => request<KnowledgeStats>("/knowledge/stats"),
  knowledgeSearch: (q: string) =>
    request<KnowledgeHit[]>(`/knowledge/search?q=${encodeURIComponent(q)}`),
  whyBatch: (ids: string[]) =>
    request<Evidence[]>("/why/batch", { method: "POST", body: JSON.stringify(ids) }),

  // --- LOT 2 ---------------------------------------------------------------
  chart: (symbol: string, timeframe: string, indicators?: string) =>
    request<ChartData>(
      `/chart/${symbol}?timeframe=${timeframe}` +
        (indicators ? `&indicators=${encodeURIComponent(indicators)}` : ""),
    ),
  etfVsPrice: (symbol: string, days = 365, lag = 0) =>
    request<EtfVsPrice>(`/etf-vs-price/${symbol}?days=${days}&lag_days=${lag}`),
  calendar: (days = 30) => request<CalendarData>(`/calendar?days=${days}`),
  dailyReport: () => request<{ text: string; generated_at: string }>("/daily-report"),
  researchEtf: (symbol: string) => request<EtfLagStudy>(`/research/etf/${symbol}`),
  researchEvents: (symbol: string) => request<EventStudyData>(`/research/events/${symbol}`),
  researchCalibration: () => request<any>("/research/calibration"),
  historyCoverage: () => request<CoverageData>("/history/coverage"),
  knowledgeDocuments: () => request<KnowledgeDocuments>("/knowledge/documents"),
  schedulerStatus: () => request<SchedulerStatus>("/scheduler/status"),

  // --- LOT 3 ---------------------------------------------------------------
  researchAudit: () => request<AuditData>("/research/audit"),
  researchAsymmetry: (symbol: string) => request<any>(`/research/asymmetry/${symbol}`),
  researchDerivatives: (symbol: string) => request<any>(`/research/derivatives/${symbol}`),
  researchRegimes: (symbol: string) => request<any>(`/research/regimes/${symbol}`),
  researchFeatures: (symbol: string, walkForward = true) =>
    request<any>(`/research/features/${symbol}?walk_forward=${walkForward}`),
  researchCandidateWeights: () => request<any>("/research/candidate-weights"),
  researchLivePerformance: () => request<any>("/research/live-performance"),

  // LOT 4: what has actually been measured, kept apart from direction.
  today: (symbol: string) => request<TodayRead>(`/today/${symbol}`),
  edge: () => request<{ assets: Record<string, EdgeAssessment>; note: string }>("/edge"),
  leverage: (symbol: string) => request<any>(`/leverage/${symbol}`),
  volatility: (symbol: string) => request<VolatilityRead>(`/volatility/${symbol}`),
  derivativesAggregate: (symbol: string) =>
    request<AggregatedDerivatives>(`/derivatives/aggregate/${symbol}`),
  researchFundingConditioned: (symbol?: string) =>
    request<any>(`/research/funding-conditioned${symbol ? `?asset=${symbol}` : ""}`),
  crossAsset: (symbol: string, window = 90) =>
    request<any>(`/cross-asset/${symbol}?window=${window}`),
  marketRatios: () => request<any>("/market/ratios"),
  marketBreadth: () => request<any>("/market/breadth"),
  marketLiquidity: () => request<any>("/market/liquidity"),
  breakout: (symbol: string, timeframe = "1d") =>
    request<any>(`/breakout/${symbol}?timeframe=${timeframe}`),
  liquidations: (symbol: string) => request<any>(`/liquidations/${symbol}`),
  researchBaselines: (symbol?: string) =>
    request<any>(`/research/baselines${symbol ? `?asset=${symbol}` : ""}`),
  researchPatterns: () => request<any>("/research/patterns"),
  researchDrift: () => request<any>("/research/drift"),
  featureRegistry: () => request<any>("/research/features"),

  // LOT 5: structure, patterns and trader knowledge.
  structure: (symbol: string, timeframe = "4h") =>
    request<StructureRead>(`/structure/${symbol}?timeframe=${timeframe}`),
  structureMultiTimeframe: (symbol: string) =>
    request<any>(`/structure/${symbol}/multi-timeframe`),
  entryOpportunity: (symbol: string, timeframe = "4h") =>
    request<any>(`/entry-opportunity/${symbol}?timeframe=${timeframe}`),
  educationalClaims: () => request<any>("/knowledge/educational-claims"),
  datasetQuality: () => request<any>("/knowledge/dataset-quality"),
  annotationQueue: (limit = 20) =>
    request<any>(`/knowledge/annotation-queue?limit=${limit}`),
  humanExamples: () => request<any>("/knowledge/examples"),
  humanVsAlgorithm: () => request<any>("/knowledge/human-vs-algorithm"),
  researchStructural: () => request<any>("/research/structural"),
  researchMarginalValue: () => request<any>("/research/marginal-value"),
  researchReplication: () => request<any>("/research/replication"),
  researchClaimValidation: () => request<any>("/research/claim-validation"),
  sourceHierarchy: () => request<any>("/sources/hierarchy"),
  snapshotsIntegrity: () => request<any>("/research/snapshots/integrity"),
  assetEmpirical: (symbol: string) => request<any>(`/assets/${symbol}/empirical`),
};

export interface AuditData {
  assets: Record<string, {
    domains: Record<string, {
      current_weight: number;
      n: number;
      ic: number | null;
      p_value: number | null;
      significant: boolean;
      monotonic: boolean;
      sign_stable_across_splits: boolean;
      stability_score: number;
      concentration?: { dominant_share: number; discriminating: boolean };
      ic_decomposition?: {
        assessable: boolean; global_ic: number | null; mean_within_ic: number | null;
        periods_positive: number; periods_total: number; globally_inflated: boolean;
        interpretation: string;
      };
      verdict: string;
      reason: string;
    }>;
    summary: {
      weight_on_useful: number;
      weight_on_worthless_or_unstable: number;
      weight_on_unmeasured: number;
      verdicts: Record<string, string[]>;
    };
  }>;
  note: string;
}

// --- LOT 2 types -----------------------------------------------------------

export interface RegimeAssessment {
  regime: string;
  regime_score: number;
  confidence: number;
  conditions: string[];
  factors: { name: string; value: string; contribution: number; weight: number; detail: string }[];
  summary: string;
  missing: string[];
  freshness: string;
  evidence_ids: string[];
}

export interface EntryTimingAssessment {
  timing: string;
  timing_score: number;
  confidence: number;
  factors: {
    name: string; value: string; contribution: number; weight: number;
    detail: string; favourable: boolean;
  }[];
  positives: string[];
  negatives: string[];
  risks: string[];
  zones_to_watch: { label: string; low: number | null; high: number | null; basis: string }[];
  invalidation_level: number | null;
  invalidation_reason: string;
  summary: string;
  missing: string[];
  explanation: string;
  evidence_ids: string[];
  freshness: string;
}

export interface ChartData {
  asset: string;
  timeframe: string;
  available: boolean;
  reason?: string;
  candles: { time: string; open: number; high: number; low: number; close: number; volume: number }[];
  overlays: Record<string, (number | null)[]>;
  panels: Record<string, (number | null)[]>;
  levels: { support: ChartLevel[]; resistance: ChartLevel[] };
  patterns: {
    pattern: string; confidence: number; state: string; direction: string;
    invalidation: number | null; notes: string;
  }[];
  markers: {
    time: string; kind: string; label: string; importance: string;
    category: string; upcoming?: boolean; direction?: string;
  }[];
}

export interface ChartLevel {
  price: number;
  touches: number;
  strength: number;
}

export interface EtfVsPrice {
  asset: string;
  available: boolean;
  reason?: string;
  lag_days: number;
  dates: string[];
  price: (number | null)[];
  flow: (number | null)[];
  ma3: (number | null)[];
  ma5: (number | null)[];
  ma7: (number | null)[];
  cumulative: (number | null)[];
  caveat: string;
}

export interface CalendarEntry {
  id?: string;
  name: string;
  category: string;
  kind: string;
  scheduled_at: string;
  hours_until: number;
  importance: string;
  assets: string[];
  certainty: string;
  source_name?: string;
  source_url?: string | null;
  legal_status?: string;
}

export interface CalendarData {
  generated_at: string;
  within_24h: CalendarEntry[];
  within_3d: CalendarEntry[];
  within_7d: CalendarEntry[];
  within_30d: CalendarEntry[];
  all_upcoming: CalendarEntry[];
  recent_regulation: CalendarEntry[];
  note: string;
}

export interface EtfLagStudy {
  asset: string;
  available: boolean;
  reason?: string;
  period?: { start: string; end: string; days: number };
  correlations?: Record<string, Record<string, {
    spearman_r: number | null; p_value: number | null; n: number;
    significant: boolean; significant_raw: boolean;
  }>>;
  contemporaneous_control?: Record<string, { spearman_r: number | null; n: number }>;
  multiple_testing?: {
    hypotheses: number; significant_raw: number; significant_after_fdr: number;
    expected_false_positives_uncorrected: number; method: string;
  };
  note?: string;
}

export interface EventStudyData {
  asset: string;
  available: boolean;
  computed?: number;
  skipped?: number;
  events: {
    event: string; label?: string; description?: string; available: boolean;
    reason?: string; occurrences?: number;
    period?: { start: string; end: string };
    horizons?: Record<string, {
      n: number; mean: number | null; median: number | null; win_rate: number | null;
      baseline_mean: number | null; edge_vs_baseline: number | null;
      reliable_sample: boolean; note: string;
      max_favorable_excursion_mean: number | null;
      max_adverse_excursion_mean: number | null;
    }>;
  }[];
}

export interface CoverageData {
  datasets: {
    dataset: string; asset: string | null; timeframe: string | null;
    earliest: string | null; latest: string | null; rows: number;
    source: string; complete: boolean; note: string; days: number;
  }[];
  per_asset: Record<string, any>;
  macro: Record<string, any>;
  snapshots: Record<string, any>;
}

export interface KnowledgeDocuments {
  documents: {
    id: string; title: string; category: string; file_type: string;
    pages: number | null; chunks: number; ingested_at: string; path: string;
  }[];
  stats: KnowledgeStats;
}

export interface SchedulerStatus {
  enabled: boolean;
  started_at: string | null;
  runs: Record<string, { at: string; ok: boolean; detail: string }>;
  last_error: { job: string; at: string; detail: string } | null;
  snapshots: Record<string, any>;
}

// --- types ---------------------------------------------------------------

export interface Health {
  status: string;
  version: string;
  mock_mode: boolean;
  llm: { enabled: boolean; provider: string; model: string | null; reason: string | null };
}

export interface AssetCard {
  asset: string;
  available: boolean;
  error?: string;
  price?: number | null;
  change_24h_pct?: number | null;
  change_7d_pct?: number | null;
  market_cap?: number | null;
  market_regime?: string;
  conviction_short?: number;
  conviction_medium?: number;
  conviction_long?: number;
  label_short?: string;
  label_medium?: string;
  confidence?: number;
  domains_available?: number;
  domains_missing?: string[];
  contradiction_strength?: number;
  generated_at?: string;
  alerts?: number;
  llm_used?: boolean;
}

export interface ScoreCard {
  domain: string;
  score: number;
  confidence: number;
  freshness: string;
  evidence_count: number;
  available: boolean;
  unavailable_reason?: string | null;
  evidence_ids?: string[];
  notes?: string[];
}

export interface Conviction {
  horizon: string;
  score: number;
  label: string;
  confidence: number;
  direction: string;
  contributors: Record<string, number>;
  capped_by_contradiction: boolean;
  rationale: string[];
}

export interface AssetDetail {
  asset: string;
  generated_at: string;
  price: number | null;
  change_24h_pct: number | null;
  change_7d_pct: number | null;
  market_cap: number | null;
  market_regime: string;
  regime: RegimeAssessment;
  entry_timing: EntryTimingAssessment;
  etf_split?: {
    available: boolean;
    context_score: number; context_label: string; context_confidence: number;
    predictive_score: number; predictive_available: boolean;
    predictive_confidence: number; predictive_reason: string;
    statement: string;
  };
  rsi_context?: {
    value: number; zone: string; regime: string;
    textbook_reading: string; measured_reading: string;
    contradicts_textbook: boolean; sample_size: number; confidence: string;
    note: string;
  };
  empirical?: {
    available: boolean; match_level: string; sample_size: number;
    horizons: Record<string, any>;
    risk_reward: { available: boolean; mfe_median?: number; mae_median?: number;
      reward_risk_ratio?: number; n?: number; interpretation?: string };
    ladder: { level: string; n: number; used: boolean }[];
    caveat: string;
  };
  probability?: {
    analytical_confidence: number; empirical_probability: number | null;
    empirical_sample: number; empirical_available: boolean;
    statement: string; methodology: string;
  };
  confrontations?: {
    topic: string; data_says: string; knowledge_says: string | null;
    agreement: string; conclusion: string;
    knowledge_citations: { document: string; excerpt: string }[];
  }[];
  scores: Record<string, ScoreCard>;
  conviction: {
    short: Conviction;
    medium: Conviction;
    long: Conviction;
    overall_confidence: number;
    domains_available: number;
    domains_missing: string[];
  };
  analysts: Record<string, AnalystResult>;
  contradictions: {
    contradictions: Contradiction[];
    max_strength: number;
    is_high: boolean;
    summary: string;
  };
  scenarios: Scenario[];
  synthesis: Synthesis;
  technical: Record<string, TechnicalSnapshot>;
  domains: Record<string, any>;
  sources: SourceStatus[];
  alerts: Alert[];
  llm_used: boolean;
  report_id: string;
}

export interface AnalystResult {
  analyst: string;
  domain: string;
  available: boolean;
  unavailable_reason?: string | null;
  score: number;
  confidence: number;
  freshness: string;
  direction: string;
  summary: string;
  positives: string[];
  negatives: string[];
  neutral: string[];
  missing_data: string[];
  evidence_ids: string[];
  knowledge_citations: { document: string; category: string; excerpt: string }[];
  llm_used: boolean;
}

export interface Contradiction {
  description: string;
  signals: string[];
  strength: number;
  domains: string[];
}

export interface Scenario {
  name: string;
  label: string;
  probability: number;
  calibrated: boolean;
  narrative: string;
  conditions: string[];
  key_levels: Record<string, number>;
  catalysts: string[];
  invalidation: string;
}

export interface Synthesis {
  text: string;
  positives: string[];
  negatives: string[];
  contradictions: string[];
  key_catalysts: string[];
  key_risks: string[];
  what_would_change_my_mind: string[];
  missing_data: string[];
  data_quality_note: string;
  llm_used: boolean;
}

export interface TechnicalSnapshot {
  timeframe: string;
  bars: number;
  price: number | null;
  freshness: string;
  trend: { direction: string; strength: number; reason: string };
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  rsi: number | null;
  rsi_state: string;
  macd_state: string;
  adx: number | null;
  atr_pct: number | null;
  volatility_state: string;
  relative_volume: number | null;
  volume_state: string;
  structure: string;
  structure_labels: string[];
  levels_support: Level[];
  levels_resistance: Level[];
  divergences: Divergence[];
  patterns: Pattern[];
  change_24h_pct: number | null;
  notes: string[];
}

export interface Level {
  price: number;
  kind: string;
  touches: number;
  strength: number;
  distance_pct: number | null;
}

export interface Divergence {
  indicator: string;
  kind: string;
  timeframe: string;
  strength: number;
}

export interface Pattern {
  pattern: string;
  confidence: number;
  timeframe: string;
  confirmation_state: string;
  invalidation_level: number | null;
  direction: string;
  notes: string;
}

export interface SourceStatus {
  capability: string;
  ok: boolean;
  provider: string;
  status: string;
  message: string;
  observations: number;
}

export interface SourcesResponse {
  asset: string;
  sources: SourceStatus[];
  ok: number;
  total: number;
}

export interface Evidence {
  id: string;
  metric: string;
  asset: string | null;
  value: unknown;
  unit: string;
  timestamp: string;
  freshness: string;
  source: string;
  provider: string;
  source_url: string | null;
  description: string;
}

export interface Alert {
  id?: number;
  kind: string;
  importance: string;
  asset: string | null;
  title: string;
  detail: string;
  triggered_at: string;
}

export interface GlobalMarket {
  generated_at: string;
  risk_regime: string;
  average_conviction: number;
  assets: { asset: string; price: number | null; change_24h_pct: number | null; conviction_medium: number; regime: string }[];
  etf: Record<string, any>;
  liquidity: any;
  macro: any;
  news: any;
  regulation: any;
  geopolitics: any;
  rwa: Record<string, any> | null;
  calendar: CalendarEvent[];
  alerts: Alert[];
}

export interface CalendarEvent {
  id: string;
  kind: string;
  name: string;
  scheduled_at: string;
  importance: string;
  hours_until: number;
}

export interface ProvidersResponse {
  mock_mode: boolean;
  providers: { name: string; available: boolean; reason: string; requires_key: string | null; configured: boolean }[];
}

export interface Evaluation {
  total_reports: number;
  evaluated_outcomes: number;
  direction_accuracy: Record<string, number | null>;
  sample_sizes: Record<string, number>;
  calibration: any[];
  by_domain: Record<string, any>;
  note: string;
}

export interface KnowledgeStats {
  documents: number;
  chunks: number;
  by_category: Record<string, number>;
  fts_available: boolean;
}

export interface KnowledgeHit {
  chunk_id: string;
  document_title: string;
  category: string;
  snippet: string;
  score: number;
  text: string;
}


// --- LOT 4 types ---------------------------------------------------------

export type EdgeState =
  | "POSITIVE_EDGE"
  | "NEGATIVE_EDGE"
  | "NO_MEASURABLE_EDGE"
  | "INSUFFICIENT_DATA";

export interface EdgeEvidence {
  source: string;
  signal: string;
  horizon_days: number | null;
  effect_pct: number | null;
  p_value: number | null;
  survives_fdr: boolean;
  effective_n: number | null;
  stability: string | null;
  admitted: boolean;
  rejection_reason: string;
}

export interface EdgeAssessment {
  asset: string;
  state: EdgeState;
  horizon_days: number | null;
  effect_pct: number | null;
  evidence: EdgeEvidence[];
  admitted_count: number;
  rejected_count: number;
  criteria: Record<string, unknown>;
  statement: string;
}

export interface UncertaintyRead {
  asset: string;
  score: number;
  level: string;
  drivers: { driver: string; contribution: number; detail: string }[];
  statement: string;
}

export interface DecisionSummary {
  asset: string;
  market_direction: string;
  direction_confidence: string | number;
  entry_timing: string;
  edge_state: EdgeState;
  crowding: string;
  volatility_regime: string;
  uncertainty: number;
  actionable: boolean;
  statement: string;
  caveats: string[];
}

export interface CrowdingRead {
  asset: string;
  level: string;
  score: number | null;
  direction: string;
  oi_percentile: number | null;
  funding_percentile: number | null;
  oi_change_7d_pct: number | null;
  components: Record<string, number>;
  interpretation: string;
  missing: string[];
}

export interface VolatilityRead {
  asset: string;
  regime: string;
  atr_percent: number | null;
  atr_percentile: number | null;
  realised_vol_annualised: number | null;
  direction: string;
  expansion_ratio: number | null;
  interpretation: string;
  note: string;
}

export interface LeverageStateRead {
  asset: string;
  state: string;
  price_change_pct: number | null;
  oi_change_pct: number | null;
  funding_band: string;
  confidence: string;
  inputs_used: string[];
  inputs_missing: string[];
  interpretation: string;
}

export interface FundingContextRead {
  asset: string;
  value: number | null;
  percentile: number | null;
  band: string;
  annualised_pct: number | null;
  history_days: number;
  sufficient_history: boolean;
  note: string;
}

export interface TodayRead {
  asset: string;
  decision_summary: DecisionSummary;
  direction_source: string;
  edge: EdgeAssessment;
  uncertainty: UncertaintyRead;
  crowding: CrowdingRead;
  leverage_state: LeverageStateRead;
  funding: FundingContextRead;
  volatility: VolatilityRead;
}

export interface ExchangeSnapshot {
  exchange: string;
  asset: string;
  funding_rate: number | null;
  open_interest_usd: number | null;
  basis_pct: number | null;
  available: boolean;
  reason: string;
}

export interface AggregatedDerivatives {
  asset: string;
  exchanges: ExchangeSnapshot[];
  funding_weighted: number | null;
  funding_simple_mean: number | null;
  funding_dispersion: number | null;
  open_interest_total_usd: number | null;
  exchange_concentration: number | null;
  dominant_exchange: string | null;
  venue_anomaly: string | null;
  available_venues: number;
  total_venues: number;
}


// --- LOT 5 types ---------------------------------------------------------

export interface ZoneRead {
  low: number;
  high: number;
  midpoint: number;
  kind: string;
  quality: {
    touches: number;
    dispersion_atr: number | null;
    median_reaction_atr: number | null;
    close_penetrations: number;
    score: number;
    components: Record<string, number>;
  };
  touch_count: number;
}

export interface RangeRead {
  range_type: string;
  valid: boolean;
  reason: string;
  top_zone: ZoneRead | null;
  bottom_zone: ZoneRead | null;
  midpoint: number | null;
  duration_bars: number;
  width_atr: number | null;
  top_touches: number;
  bottom_touches: number;
  deviations: any[];
  confidence: number;
}

export interface LocationRead {
  asset: string;
  timeframe: string;
  state: string;
  price: number | null;
  relative_position: number | null;
  distance_to_top_atr: number | null;
  distance_to_bottom_atr: number | null;
  range_summary: string;
  invalidation: string;
  explanation: string[];
  range: RangeRead | null;
}

export interface PatternRead {
  name: string;
  pattern_class: string;
  state: string;
  recognition_confidence: number;
  detected_at: string;
  direction_if_textbook: string;
  key_levels: Record<string, number>;
  invalidation_level: number | null;
  invalidation_rule: string;
  components: Record<string, unknown>;
  edge_state: string;
  notes: string;
  separation_note: string;
}

export interface MarketStructureRead {
  asset: string;
  timeframe: string;
  state: string;
  labels: string[];
  last_confirmed_hh: number | null;
  last_confirmed_hl: number | null;
  last_confirmed_lh: number | null;
  last_confirmed_ll: number | null;
  events: {
    kind: string;
    direction: string;
    level: number;
    broken_at: string;
    confirmation_time: string;
    note: string;
  }[];
  interpretation: string;
  caveat: string;
}

export interface StructureRead {
  asset: string;
  timeframe: string;
  location: LocationRead;
  market_structure: MarketStructureRead;
  patterns: PatternRead[];
  separation_note: string;
}
