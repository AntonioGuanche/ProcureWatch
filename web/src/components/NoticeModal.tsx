import { useEffect, useState } from "react";
import { getNotice, getNoticeLots, getNoticeDocuments, addFavorite, removeFavorite, generateSummary } from "../api";
import type { Notice, NoticeLot, NoticeDocument, AISummaryResponse } from "../types";

function fmtDate(s: string | null): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("fr-BE", { day: "2-digit", month: "long", year: "numeric" }); }
  catch { return s; }
}

function fmtValue(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("fr-BE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);
}

function orgName(names: Record<string, string> | null): string {
  if (!names) return "—";
  return names.fr || names.nl || names.en || names.de || Object.values(names)[0] || "—";
}

const LANG_OPTIONS = [
  { value: "fr", label: "Français" },
  { value: "nl", label: "Nederlands" },
  { value: "en", label: "English" },
  { value: "de", label: "Deutsch" },
];

interface Props {
  noticeId: string;
  isFavorited: boolean;
  onToggleFavorite: (noticeId: string, favorited: boolean) => void;
  onClose: () => void;
}

export function NoticeModal({ noticeId, isFavorited, onToggleFavorite, onClose }: Props) {
  const [notice, setNotice] = useState<Notice | null>(null);
  const [lots, setLots] = useState<NoticeLot[]>([]);
  const [docs, setDocs] = useState<NoticeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [favLoading, setFavLoading] = useState(false);

  // AI Summary state
  const [summaryData, setSummaryData] = useState<AISummaryResponse | null>(null);
  const [summaryLang, setSummaryLang] = useState("fr");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setSummaryData(null);
    setSummaryError(null);
    Promise.all([
      getNotice(noticeId),
      getNoticeLots(noticeId).catch(() => ({ items: [], total: 0 })),
      getNoticeDocuments(noticeId).catch(() => ({ items: [], total: 0 })),
    ]).then(([n, l, d]) => {
      setNotice(n);
      setLots(l.items);
      setDocs(d.items);
      // If notice already has a cached summary, show it
      if (n.ai_summary) {
        setSummaryData({
          notice_id: n.id,
          summary: n.ai_summary,
          lang: n.ai_summary_lang || "fr",
          generated_at: n.ai_summary_generated_at,
          cached: true,
        });
        if (n.ai_summary_lang) setSummaryLang(n.ai_summary_lang);
      }
    }).finally(() => setLoading(false));
  }, [noticeId]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const handleFav = async () => {
    setFavLoading(true);
    try {
      if (isFavorited) {
        await removeFavorite(noticeId);
        onToggleFavorite(noticeId, false);
      } else {
        await addFavorite(noticeId);
        onToggleFavorite(noticeId, true);
      }
    } catch { /* ignore */ }
    finally { setFavLoading(false); }
  };

  const handleGenerateSummary = async (force = false) => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const data = await generateSummary(noticeId, summaryLang, force);
      setSummaryData(data);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : "Erreur lors de la génération du résumé");
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleLangChange = (lang: string) => {
    setSummaryLang(lang);
    // If we already have a summary in a different language, regenerate
    if (summaryData && summaryData.lang !== lang) {
      setSummaryData(null);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{notice?.title || "Chargement…"}</h2>
          <div className="modal-header-actions">
            <button
              className={`btn-icon ${isFavorited ? "favorited" : ""}`}
              onClick={handleFav}
              disabled={favLoading}
              title={isFavorited ? "Retirer des favoris" : "Ajouter aux favoris"}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill={isFavorited ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
            </button>
            <button className="btn-icon" onClick={onClose} title="Fermer">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        {loading ? (
          <div className="modal-body"><div className="loading">Chargement…</div></div>
        ) : notice ? (
          <div className="modal-body">
            {/* Meta grid */}
            <div className="notice-meta-grid">
              <div className="meta-item">
                <span className="meta-label">Acheteur</span>
                <span className="meta-value">{orgName(notice.organisation_names)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Source</span>
                <span className={`source-badge ${notice.source.includes("BOSA") ? "bosa" : "ted"}`}>
                  {notice.source.includes("BOSA") ? "BOSA" : "TED"}
                </span>
              </div>
              <div className="meta-item">
                <span className="meta-label">CPV</span>
                <span className="meta-value"><code>{notice.cpv_main_code || "—"}</code></span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Publication</span>
                <span className="meta-value">{fmtDate(notice.publication_date)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Deadline</span>
                <span className="meta-value">{fmtDate(notice.deadline)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Valeur estimée</span>
                <span className="meta-value">{fmtValue(notice.estimated_value)}</span>
              </div>
              {notice.notice_type && (
                <div className="meta-item">
                  <span className="meta-label">Type</span>
                  <span className="meta-value">{notice.notice_type}</span>
                </div>
              )}
              {notice.form_type && (
                <div className="meta-item">
                  <span className="meta-label">Formulaire</span>
                  <span className="meta-value">{notice.form_type}</span>
                </div>
              )}
              {notice.nuts_codes && notice.nuts_codes.length > 0 && (
                <div className="meta-item">
                  <span className="meta-label">Zones NUTS</span>
                  <span className="meta-value">{notice.nuts_codes.join(", ")}</span>
                </div>
              )}
              {notice.reference_number && (
                <div className="meta-item">
                  <span className="meta-label">Référence</span>
                  <span className="meta-value">{notice.reference_number}</span>
                </div>
              )}
              {notice.status && (
                <div className="meta-item">
                  <span className="meta-label">Statut</span>
                  <span className="meta-value">{notice.status}</span>
                </div>
              )}
            </div>

            {/* Award info (CAN) */}
            {(notice.award_winner_name || notice.award_value || notice.award_date) && (
              <div className="notice-section notice-award-section">
                <h3>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/>
                  </svg>
                  Attribution
                </h3>
                <div className="award-grid">
                  {notice.award_winner_name && (
                    <div className="award-item">
                      <span className="award-label">Adjudicataire</span>
                      <span className="award-value award-winner">{notice.award_winner_name}</span>
                    </div>
                  )}
                  {notice.award_value != null && (
                    <div className="award-item">
                      <span className="award-label">Montant attribué</span>
                      <span className="award-value">{fmtValue(notice.award_value)}</span>
                    </div>
                  )}
                  {notice.award_date && (
                    <div className="award-item">
                      <span className="award-label">Date d'attribution</span>
                      <span className="award-value">{fmtDate(notice.award_date)}</span>
                    </div>
                  )}
                  {notice.number_tenders_received != null && (
                    <div className="award-item">
                      <span className="award-label">Offres reçues</span>
                      <span className="award-value">{notice.number_tenders_received}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Description */}
            {notice.description && (
              <div className="notice-section">
                <h3>Description</h3>
                <p className="notice-description">{notice.description}</p>
              </div>
            )}

            {/* AI Summary */}
            <div className="notice-section notice-ai-section">
              <div className="ai-section-header">
                <h3>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2a4 4 0 014 4c0 1.95-1.4 3.58-3.25 3.93L12 22"/>
                    <path d="M8 6a4 4 0 018 0"/>
                    <path d="M17 12.5c1.65.46 3 1.93 3 3.5a4 4 0 01-4 4H8a4 4 0 01-4-4c0-1.57 1.35-3.04 3-3.5"/>
                  </svg>
                  Résumé IA
                </h3>
                <div className="ai-controls">
                  <select
                    className="ai-lang-select"
                    value={summaryLang}
                    onChange={(e) => handleLangChange(e.target.value)}
                    disabled={summaryLoading}
                  >
                    {LANG_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  {!summaryData ? (
                    <button
                      className="btn-sm btn-ai"
                      onClick={() => handleGenerateSummary(false)}
                      disabled={summaryLoading}
                    >
                      {summaryLoading ? (
                        <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg> Génération…</>
                      ) : (
                        "Générer le résumé"
                      )}
                    </button>
                  ) : (
                    <button
                      className="btn-sm btn-outline"
                      onClick={() => handleGenerateSummary(true)}
                      disabled={summaryLoading}
                      title="Regénérer dans la langue sélectionnée"
                    >
                      {summaryLoading ? (
                        <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg></>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
                      )}
                    </button>
                  )}
                </div>
              </div>

              {summaryError && (
                <div className="ai-error">{summaryError}</div>
              )}

              {summaryData && (
                <div className="ai-summary-content">
                  <p>{summaryData.summary}</p>
                  <div className="ai-summary-meta">
                    {summaryData.cached && <span className="ai-cached-badge">en cache</span>}
                    <span className="ai-lang-badge">{LANG_OPTIONS.find((o) => o.value === summaryData.lang)?.label || summaryData.lang}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Lots */}
            {lots.length > 0 && (
              <div className="notice-section">
                <h3>Lots ({lots.length})</h3>
                <div className="lots-list">
                  {lots.map((lot) => (
                    <div key={lot.id} className="lot-item">
                      <div className="lot-header">
                        <strong>Lot {lot.lot_number || "?"}</strong>
                        {lot.cpv_code && <code className="cpv-code">{lot.cpv_code}</code>}
                      </div>
                      {lot.title && <div className="lot-title">{lot.title}</div>}
                      {lot.description && <p className="lot-desc">{lot.description}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Documents */}
            {docs.length > 0 && (
              <div className="notice-section">
                <h3>Documents ({docs.length})</h3>
                <div className="docs-list">
                  {docs.map((doc) => (
                    <a key={doc.id} href={doc.url} target="_blank" rel="noopener noreferrer" className="doc-item">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                      <span>{doc.title || "Document"}</span>
                      {doc.file_type && <span className="doc-type">{doc.file_type}</span>}
                      {doc.language && <span className="doc-lang">{doc.language.toUpperCase()}</span>}
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* URL */}
            {notice.url && (
              <div className="notice-section">
                <a href={notice.url} target="_blank" rel="noopener noreferrer" className="btn-primary" style={{ display: "inline-block", textDecoration: "none" }}>
                  Voir l'avis original ↗
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="modal-body"><div className="alert alert-error">Notice introuvable</div></div>
        )}
      </div>
    </div>
  );
}
