/** Backend schema types (match FastAPI Pydantic models). */

// ── Notices ─────────────────────────────────────────────────────────

export interface NoticeSearchItem {
  id: string;
  title: string;
  source: string;
  cpv_main_code: string | null;
  nuts_codes: string[] | null;
  organisation_names: Record<string, string> | null;
  publication_date: string | null;
  deadline: string | null;
  reference_number: string | null;
  description: string | null;
  notice_type: string | null;
  form_type: string | null;
  estimated_value: number | null;
  url: string | null;
  status: string | null;
  // CAN (Contract Award Notice) fields
  award_winner_name: string | null;
  award_value: number | null;
  award_date: string | null;
  number_tenders_received: number | null;
}

export interface NoticeSearchResponse {
  items: NoticeSearchItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Notice {
  id: string;
  source: string;
  source_id: string;
  title: string;
  description: string | null;
  cpv_main_code: string | null;
  nuts_codes: string[] | null;
  organisation_names: Record<string, string> | null;
  publication_date: string | null;
  deadline: string | null;
  estimated_value: number | null;
  notice_type: string | null;
  form_type: string | null;
  url: string | null;
  status: string | null;
  reference_number: string | null;
  // CAN (Contract Award Notice) fields
  award_winner_name: string | null;
  award_value: number | null;
  award_date: string | null;
  number_tenders_received: number | null;
  // AI summary
  ai_summary: string | null;
  ai_summary_lang: string | null;
  ai_summary_generated_at: string | null;
  // Timestamps
  created_at: string;
  updated_at: string;
}

export interface NoticeListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Notice[];
}

// ── AI Summary ──────────────────────────────────────────────────────

export interface AISummaryResponse {
  notice_id: string;
  summary: string;
  lang: string;
  generated_at: string | null;
  cached: boolean;
}

// ── Document AI Analysis (Phase 2) ─────────────────────────────────

export interface DocumentAnalysisConditions {
  capacite_technique: string | null;
  capacite_financiere: string | null;
  agreations: string[] | null;
  certifications: string[] | null;
}

export interface DocumentAnalysisBudget {
  valeur_estimee: string | null;
  cautionnement: string | null;
}

export interface DocumentAnalysisCalendar {
  date_limite: string | null;
  duree_marche: string | null;
  delai_execution: string | null;
  visite_obligatoire: string | null;
}

export interface DocumentAnalysisResult {
  objet: string | null;
  lots: string[] | null;
  criteres_attribution: string[] | null;
  conditions_participation: DocumentAnalysisConditions | null;
  budget: DocumentAnalysisBudget | null;
  calendrier: DocumentAnalysisCalendar | null;
  points_attention: string[] | null;
  score_accessibilite_pme: string | null;
  // fallback if JSON parsing fails
  raw_text?: string;
}

export interface DocumentAnalysisResponse {
  notice_id: string;
  document_id: string;
  status: "ok" | "no_text" | "error";
  message?: string;
  analysis?: DocumentAnalysisResult;
  generated_at?: string | null;
  cached?: boolean;
}

// ── Facets ──────────────────────────────────────────────────────────

export interface FacetItem {
  value?: string;
  code?: string;
  label?: string;
  count: number;
}

export interface FacetsResponse {
  total_notices: number;
  active_count: number;
  sources: FacetItem[];
  top_cpv_divisions: FacetItem[];
  top_nuts_countries: FacetItem[];
  notice_types: FacetItem[];
  date_range: { min: string; max: string };
  deadline_range: { min: string; max: string };
  value_range: { min: number | null; max: number | null };
}

// ── Dashboard ───────────────────────────────────────────────────────

export interface DashboardOverview {
  total_notices: number;
  active_notices: number;
  expiring_7d: number;
  by_source: Record<string, number>;
  added_24h: number;
  added_7d: number;
  newest_publication: string | null;
  oldest_publication: string | null;
  value_stats: {
    notices_with_value: number;
    min_eur: number | null;
    max_eur: number | null;
    avg_eur: number | null;
  };
}

export interface TrendPoint {
  source: string;
  date: string;
  count: number;
}

export interface DashboardTrends {
  period_days: number;
  group_by: string;
  cutoff: string;
  totals_by_source: Record<string, number>;
  data: TrendPoint[];
}

export interface CpvItem {
  code: string;
  label: string;
  count: number;
}

export interface DashboardTopCpv {
  active_only: boolean;
  data: CpvItem[];
}

export interface AuthorityItem {
  name: string;
  count: number;
}

export interface DashboardTopAuthorities {
  active_only: boolean;
  data: AuthorityItem[];
}

export interface DashboardHealth {
  imports: Record<string, {
    last_run: string | null;
    total_created: number;
    total_updated: number;
    total_errors: number;
    run_count: number;
  }>;
  freshness: {
    newest_publication_date: string | null;
    newest_record_created: string | null;
    hours_since_last_import: number | null;
  };
  field_fill_rates_pct: Record<string, number>;
}

// ── Watchlists ──────────────────────────────────────────────────────

export interface Watchlist {
  id: string;
  name: string;
  keywords: string[];
  countries: string[];
  cpv_prefixes: string[];
  nuts_prefixes: string[];
  sources: string[];
  enabled: boolean;
  notify_email: string | null;
  last_refresh_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WatchlistListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Watchlist[];
}

export interface WatchlistCreate {
  name: string;
  keywords?: string[];
  countries?: string[];
  cpv_prefixes?: string[];
  nuts_prefixes?: string[];
  sources?: string[];
  enabled?: boolean;
  notify_email?: string | null;
}

export interface WatchlistUpdate {
  name?: string;
  keywords?: string[];
  countries?: string[];
  cpv_prefixes?: string[];
  nuts_prefixes?: string[];
  sources?: string[];
  enabled?: boolean;
  notify_email?: string | null;
}

export interface WatchlistMatchRead {
  notice: Notice;
  matched_on: string;
  relevance_score: number | null;
}

export interface WatchlistMatchesResponse {
  total: number;
  page: number;
  page_size: number;
  items: WatchlistMatchRead[];
}

export interface RefreshSummary {
  matched: number;
  added: number;
}

// ── Notice Detail (lots, documents) ─────────────────────────────────

export interface NoticeLot {
  id: string;
  notice_id: string;
  lot_number: string | null;
  title: string | null;
  description: string | null;
  cpv_code: string | null;
  nuts_code: string | null;
}

export interface NoticeDocument {
  id: string;
  notice_id: string;
  lot_id: string | null;
  title: string | null;
  url: string;
  file_type: string | null;
  language: string | null;
  // Download pipeline status
  download_status: string | null;   // ok | failed | skipped | null
  extraction_status: string | null; // ok | skipped | failed | null
  file_size: number | null;
  // Phase 2: AI analysis indicator
  has_ai_analysis: boolean;
  ai_analysis_generated_at: string | null;
}

// ── Document Q&A (Phase 3) ────────────────────────────────────────

export interface QASource {
  document_id: string | null;
  title: string;
  file_type: string | null;
  text_length: number;
}

export interface QAResponse {
  status: "ok" | "no_content" | "no_documents" | "error";
  answer: string | null;
  question?: string;
  message?: string;
  sources: QASource[];
  documents_used?: number;
  notice_data_used?: boolean;
  lang?: string;
}

// ── Document Upload (Phase 3) ────────────────────────────────────

export interface UploadResponse {
  status: "ok" | "duplicate";
  document_id: string;
  filename?: string;
  file_size?: number;
  text_length?: number;
  has_text?: boolean;
  message: string;
}

export interface DownloadResponse {
  status: "ok" | "already_done" | "blocked" | "skipped" | "failed";
  document_id: string;
  download_status?: string;
  extraction_status?: string;
  text_length?: number;
  has_text?: boolean;
  file_size?: number;
  message: string;
}

export interface DiscoverResponse {
  status: "ok" | "no_workspace" | "no_documents" | "not_supported";
  source: string;
  message: string;
  documents_created: number;
  total_found?: number;
  already_existing?: number;
  skipped_non_pdf?: number;
  errors?: number;
}

// ── Favorites ───────────────────────────────────────────────────────

export interface FavoriteItem {
  notice: Notice;
  favorited_at: string;
}

export interface FavoriteListResponse {
  total: number;
  page: number;
  page_size: number;
  items: FavoriteItem[];
}

export interface FavoriteIdsResponse {
  notice_ids: string[];
}

// ── CPV Intelligence ──────────────────────────────────────────────

export interface CpvGroupOption {
  code: string;
  label: string;
}

export interface CpvVolumeTotals {
  total_notices: number;
  total_awarded: number;
  sum_estimated_eur: number;
  sum_awarded_eur: number;
  avg_estimated_eur: number;
  avg_awarded_eur: number;
}

export interface CpvMonthlyPoint {
  month: string;
  count: number;
  awarded: number;
  total_estimated: number;
  total_awarded: number;
  avg_estimated: number;
  avg_awarded: number;
}

export interface CpvYearlyPoint {
  year: number;
  count: number;
  awarded: number;
  total_estimated: number;
  total_awarded: number;
}

export interface CpvWinner {
  name: string;
  contracts_won: number;
  total_value_eur: number;
  avg_value_eur: number;
  first_award: string | null;
  last_award: string | null;
}

export interface CpvBuyer {
  name: string;
  notice_count: number;
  awarded_count: number;
  total_estimated_eur: number;
  total_awarded_eur: number;
}

export interface CompetitionBucket {
  label: string;
  count: number;
  pct: number;
}

export interface CpvCompetition {
  total_with_data: number;
  avg_tenders: number;
  median_tenders: number;
  min_tenders: number | null;
  max_tenders: number | null;
  distribution: CompetitionBucket[];
}

export interface CpvProcedureType {
  type: string;
  count: number;
  pct: number;
}

export interface CpvGeoItem {
  nuts_code: string;
  label: string;
  count: number;
}

export interface CpvSeasonalityPoint {
  month: number;
  month_name: string;
  total: number;
  avg_per_year: number;
}

export interface ValueBucket {
  label: string;
  count: number;
  pct: number;
}

export interface CpvValueDistribution {
  estimated: { total_with_value: number; buckets: ValueBucket[] };
  awarded: { total_with_value: number; buckets: ValueBucket[] };
}

export interface SingleBidContract {
  id: string;
  title: string;
  winner: string;
  award_value_eur: number | null;
  estimated_value_eur: number | null;
  award_date: string | null;
  source: string;
}

export interface CpvAwardTimeline {
  total_with_data: number;
  avg_days: number | null;
  median_days: number | null;
  min_days: number | null;
  max_days: number | null;
  p25_days: number | null;
  p75_days: number | null;
}

export interface ActiveOpportunity {
  id: string;
  title: string;
  source: string;
  deadline: string | null;
  days_left: number | null;
  estimated_value_eur: number | null;
  cpv_code: string | null;
  buyer: string | null;
  url: string | null;
}

export interface CpvAnalysisResponse {
  cpv_groups: CpvGroupOption[];
  generated_at: string;
  volume_value: {
    totals: CpvVolumeTotals;
    monthly: CpvMonthlyPoint[];
    yearly: CpvYearlyPoint[];
  };
  top_winners: CpvWinner[];
  top_buyers: CpvBuyer[];
  competition: CpvCompetition;
  procedure_types: CpvProcedureType[];
  geography: CpvGeoItem[];
  seasonality: CpvSeasonalityPoint[];
  value_distribution: CpvValueDistribution;
  single_bid_contracts: { total_single_bid: number; recent: SingleBidContract[] };
  award_timeline: CpvAwardTimeline;
  active_opportunities: { total_active: number; notices: ActiveOpportunity[] };
}
