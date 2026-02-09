/**
 * API client for ProcureWatch backend.
 * 
 * In dev: Vite proxy forwards /api/* to the backend (see vite.config.ts).
 * In prod: Set VITE_API_BASE_URL to the backend URL.
 */

// Always use relative URLs — Vite proxy forwards /api/* to the backend
const API_BASE = "";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    let detail: string;
    try {
      const j = JSON.parse(text);
      detail = j.detail ?? text;
    } catch {
      detail = text || res.statusText;
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

import type {
  Watchlist,
  WatchlistListResponse,
  WatchlistCreate,
  WatchlistUpdate,
  NoticeListResponse,
  NoticeSearchResponse,
  FacetsResponse,
  DashboardOverview,
  DashboardTrends,
  DashboardTopCpv,
  DashboardTopAuthorities,
  DashboardHealth,
  RefreshSummary,
} from "./types";

// ── Search & Facets ─────────────────────────────────────────────────

export interface SearchParams {
  q?: string;
  cpv?: string;
  nuts?: string;
  source?: string;
  authority?: string;
  notice_type?: string;
  date_from?: string;
  date_to?: string;
  deadline_after?: string;
  value_min?: number;
  value_max?: number;
  active_only?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
}

export function searchNotices(params: SearchParams): Promise<NoticeSearchResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      qs.set(k, String(v));
    }
  }
  return request(`/api/notices/search?${qs}`);
}

export function getFacets(): Promise<FacetsResponse> {
  return request("/api/notices/facets");
}

// ── Dashboard ───────────────────────────────────────────────────────

export function getDashboardOverview(): Promise<DashboardOverview> {
  return request("/api/dashboard/overview");
}

export function getDashboardTrends(days = 30, groupBy = "day"): Promise<DashboardTrends> {
  return request(`/api/dashboard/trends?days=${days}&group_by=${groupBy}`);
}

export function getDashboardTopCpv(limit = 15, activeOnly = false): Promise<DashboardTopCpv> {
  return request(`/api/dashboard/top-cpv?limit=${limit}&active_only=${activeOnly}`);
}

export function getDashboardTopAuthorities(limit = 15, activeOnly = false): Promise<DashboardTopAuthorities> {
  return request(`/api/dashboard/top-authorities?limit=${limit}&active_only=${activeOnly}`);
}

export function getDashboardHealth(): Promise<DashboardHealth> {
  return request("/api/dashboard/health");
}

// ── Watchlists ──────────────────────────────────────────────────────

export function listWatchlists(page = 1, pageSize = 50): Promise<WatchlistListResponse> {
  return request(`/api/watchlists?page=${page}&page_size=${pageSize}`);
}

export function getWatchlist(id: string): Promise<Watchlist> {
  return request(`/api/watchlists/${id}`);
}

export function createWatchlist(payload: WatchlistCreate): Promise<Watchlist> {
  return request("/api/watchlists", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateWatchlist(id: string, payload: WatchlistUpdate): Promise<Watchlist> {
  return request(`/api/watchlists/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteWatchlist(id: string): Promise<void> {
  return request(`/api/watchlists/${id}`, { method: "DELETE" });
}

export function refreshWatchlist(id: string): Promise<RefreshSummary> {
  return request(`/api/watchlists/${id}/refresh`, { method: "POST" });
}

export function previewWatchlist(
  id: string,
  page = 1,
  pageSize = 25
): Promise<NoticeListResponse> {
  return request(
    `/api/watchlists/${id}/preview?page=${page}&page_size=${pageSize}`
  );
}

export function newSinceWatchlist(
  id: string,
  page = 1,
  pageSize = 25
): Promise<NoticeListResponse> {
  return request(
    `/api/watchlists/${id}/new?page=${page}&page_size=${pageSize}`
  );
}
