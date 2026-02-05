/** Backend schema types (match FastAPI Pydantic models). */

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
