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
  buyer_name: string | null;
  country: string | null;
  language: string | null;
  cpv: string | null;
  cpv_main_code: string | null;
  procedure_type: string | null;
  published_at: string | null;
  deadline_at: string | null;
  url: string;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface NoticeListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Notice[];
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
  is_enabled: boolean;
  term: string | null;
  cpv_prefix: string | null;
  buyer_contains: string | null;
  procedure_type: string | null;
  country: string;
  language: string | null;
  notify_email: string | null;
  last_refresh_at: string | null;
  last_refresh_status: string | null;
  last_notified_at: string | null;
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
  is_enabled?: boolean;
  term?: string | null;
  cpv_prefix?: string | null;
  buyer_contains?: string | null;
  procedure_type?: string | null;
  country?: string;
  language?: string | null;
  notify_email?: string | null;
}

export interface WatchlistUpdate {
  name?: string;
  is_enabled?: boolean;
  term?: string | null;
  cpv_prefix?: string | null;
  buyer_contains?: string | null;
  procedure_type?: string | null;
  country?: string;
  language?: string | null;
  notify_email?: string | null;
}

export interface RefreshSummary {
  watchlist_id: string;
  pages_fetched: number;
  fetched_total: number;
  imported_new_total: number;
  imported_updated_total: number;
  errors_total: number;
}
