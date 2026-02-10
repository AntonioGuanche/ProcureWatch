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

export interface WatchlistMatchesResponse {
  total: number;
  page: number;
  page_size: number;
  items: WatchlistMatchRead[];
}

export interface WatchlistMatchRead {
  notice: Notice;
  matched_on: string;
}

export interface RefreshSummary {
  matched: number;
  added: number;
}

/* ── Chip Input ────────────────────────────────────────────────────── */

.chip-input-container {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--gray-300, #d1d5db);
  border-radius: var(--radius, 6px);
  background: white;
  cursor: text;
  min-height: 2.25rem;
  align-items: center;
}
.chip-input-container:focus-within {
  border-color: var(--primary, #2563eb);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: var(--gray-100, #f3f4f6);
  border: 1px solid var(--gray-200, #e5e7eb);
  border-radius: 999px;
  padding: 0.15rem 0.5rem;
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--gray-800, #1f2937);
  white-space: nowrap;
}

.chip-remove {
  all: unset;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  color: var(--gray-400, #9ca3af);
  padding: 0 0.1rem;
  border-radius: 50%;
}
.chip-remove:hover {
  color: var(--danger, #dc2626);
}

.chip-input {
  all: unset;
  flex: 1;
  min-width: 80px;
  font-size: 0.87rem;
  padding: 0.1rem 0;
}

/* ── Filter badges on detail page ──────────────────────────────────── */

.filter-badge {
  display: inline-block;
  background: var(--gray-100, #f3f4f6);
  border: 1px solid var(--gray-200, #e5e7eb);
  border-radius: var(--radius, 6px);
  padding: 0.2rem 0.6rem;
  font-size: 0.82rem;
  margin-right: 0.4rem;
  margin-bottom: 0.25rem;
}

.wl-filters {
  margin-bottom: 0.5rem;
}
