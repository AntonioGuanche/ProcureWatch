/**
 * API client for ProcureWatch backend.
 * Base URL from env VITE_API_BASE_URL (default http://127.0.0.1:8000).
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  RefreshSummary,
} from "./types";

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
