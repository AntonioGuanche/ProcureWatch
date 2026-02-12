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
  WatchlistMatchesResponse,
  WatchlistCreate,
  WatchlistUpdate,
  NoticeListResponse,
  NoticeSearchResponse,
  AISummaryResponse,
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
  pageSize = 25,
  filters?: { source?: string; q?: string; sort?: string; active_only?: boolean }
): Promise<NoticeListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters?.source) params.set("source", filters.source);
  if (filters?.q) params.set("q", filters.q);
  if (filters?.sort) params.set("sort", filters.sort);
  if (filters?.active_only) params.set("active_only", "true");
  return request(`/api/watchlists/${id}/preview?${params}`);
}

export function newSinceWatchlist(
  id: string,
  page = 1,
  pageSize = 25,
  filters?: { source?: string; q?: string; sort?: string; active_only?: boolean }
): Promise<NoticeListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters?.source) params.set("source", filters.source);
  if (filters?.q) params.set("q", filters.q);
  if (filters?.sort) params.set("sort", filters.sort);
  if (filters?.active_only) params.set("active_only", "true");
  return request(`/api/watchlists/${id}/new?${params}`);
}

export function getWatchlistMatches(
  id: string,
  page = 1,
  pageSize = 25,
): Promise<WatchlistMatchesResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return request(`/api/watchlists/${id}/matches?${params}`);
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

// ── AI Summary ──────────────────────────────────────────────────────

export function generateSummary(
  noticeId: string,
  lang = "fr",
  force = false,
): Promise<AISummaryResponse> {
  const params = new URLSearchParams({ lang });
  if (force) params.set("force", "true");
  return request(`/api/notices/${noticeId}/summary?${params}`, { method: "POST" });
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

// ── Profile ─────────────────────────────────────────────────────────

export interface FullProfile {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  company_name: string | null;
  vat_number: string | null;
  nace_codes: string | null;
  address: string | null;
  postal_code: string | null;
  city: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
}

export function getProfile(): Promise<FullProfile> {
  return request("/api/auth/me");
}

export function updateProfile(data: {
  name?: string;
  email?: string;
  company_name?: string;
  vat_number?: string;
  nace_codes?: string;
  address?: string;
  postal_code?: string;
  city?: string;
  country?: string;
}): Promise<FullProfile> {
  return request("/api/auth/profile", { method: "PUT", body: JSON.stringify(data) });
}

export function changePassword(data: { current_password: string; new_password: string }): Promise<{ status: string }> {
  return request("/api/auth/password", { method: "PUT", body: JSON.stringify(data) });
}

export function deleteAccount(): Promise<{ status: string }> {
  return request("/api/auth/account", { method: "DELETE" });
}

// ── Billing ─────────────────────────────────────────────────────────

export interface SubscriptionInfo {
  plan: string;
  effective_plan: string;
  display_name: string;
  status: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  limits: {
    max_watchlists: number;
    max_results_per_watchlist: number;
    email_digest: boolean;
    csv_export: boolean;
    api_access: boolean;
    ai_summaries_per_month: number;
    max_seats: number;
    history_days: number;
  };
}

export interface PlanInfo {
  name: string;
  display_name: string;
  price_monthly_eur: number;
  price_annual_eur: number;
  features: Record<string, unknown>;
}

export function getSubscription(): Promise<SubscriptionInfo> {
  return request("/api/billing/subscription");
}

export function getPlans(): Promise<PlanInfo[]> {
  return request("/api/billing/plans");
}

export function createCheckout(plan: string, interval: string = "month"): Promise<{ checkout_url: string }> {
  return request("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan, interval }),
  });
}

export function createPortalSession(): Promise<{ portal_url: string }> {
  return request("/api/billing/portal", { method: "POST" });
}

// ── Admin ───────────────────────────────────────────────────────────

export function getAdminStats(): Promise<{ users: { total: number; active: number }; watchlists: { total: number; enabled: number }; favorites_total: number }> {
  return request("/api/admin/stats");
}

export function getAdminUsers(): Promise<Array<{ id: string; email: string; name: string; is_admin: boolean; is_active: boolean; plan: string; subscription_status: string; created_at: string | null }>> {
  return request("/api/admin/users");
}

export function adminSetPlan(userId: string, plan: string): Promise<{ status: string; email: string; old_plan: string; new_plan: string }> {
  return request(`/api/admin/users/${userId}/plan?plan=${plan}`, { method: "PUT" });
}
