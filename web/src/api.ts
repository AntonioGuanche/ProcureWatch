/**
 * API client for ProcureWatch backend.
 * Auth token is read from sessionStorage and injected automatically.
 */

const API_BASE = "";
const TOKEN_KEY = "pw_token";

function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string> || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(url, {
    ...options,
    headers,
  });

  // Auto-logout on 401
  if (res.status === 401) {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem("pw_user");
    window.location.reload();
    throw new Error("Session expirée");
  }

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
  Watchlist,
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

// ── Notice Detail ───────────────────────────────────────────────────

export function getNotice(id: string): Promise<import("./types").Notice> {
  return request(`/api/notices/${id}`);
}

export function getNoticeLots(noticeId: string): Promise<{ items: import("./types").NoticeLot[]; total: number }> {
  return request(`/api/notices/${noticeId}/lots?page_size=50`);
}

export function getNoticeDocuments(noticeId: string): Promise<{ items: import("./types").NoticeDocument[]; total: number }> {
  return request(`/api/notices/${noticeId}/documents?page_size=50`);
}

// ── Favorites ───────────────────────────────────────────────────────

export function listFavorites(page = 1, pageSize = 25): Promise<import("./types").FavoriteListResponse> {
  return request(`/api/favorites?page=${page}&page_size=${pageSize}`);
}

export function getFavoriteIds(): Promise<import("./types").FavoriteIdsResponse> {
  return request(`/api/favorites/ids`);
}

export function addFavorite(noticeId: string): Promise<{ status: string }> {
  return request(`/api/favorites/${noticeId}`, { method: "POST" });
}

export function removeFavorite(noticeId: string): Promise<{ status: string }> {
  return request(`/api/favorites/${noticeId}`, { method: "DELETE" });
}
