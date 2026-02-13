import { useEffect, useState } from "react";
import { getNotice, getNoticeLots, getNoticeDocuments, addFavorite, removeFavorite, generateSummary, analyzeDocument, askNoticeQuestion, uploadDocument, downloadDocument, discoverDocuments } from "../api";
import type { Notice, NoticeLot, NoticeDocument, AISummaryResponse, DocumentAnalysisResponse, QAResponse } from "../types";

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

function isPdfDoc(doc: NoticeDocument): boolean {
  const ft = (doc.file_type || "").toLowerCase();
  if (ft.includes("pdf")) return true;
  const url = (doc.url || "").toLowerCase();
  return url.endsWith(".pdf") || url.includes(".pdf?");
}

const LANG_OPTIONS = [
  { value: "fr", label: "Français" },
  { value: "nl", label: "Nederlands" },
  { value: "en", label: "English" },
  { value: "de", label: "Deutsch" },
];

const PME_SCORE_COLORS: Record<string, string> = {
  facile: "#16a34a",
  moyen: "#d97706",
  difficile: "#dc2626",
};

interface Props {
  noticeId: string;
  isFavorited: boolean;
  onToggleFavorite: (noticeId: string, favorited: boolean) => void;
  onClose: () => void;
}

// ── Document Analysis Panel ─────────────────────────────────────

function AnalysisPanel({ data }: { data: DocumentAnalysisResponse }) {
  if (data.status === "no_text") {
    return <div className="analysis-message analysis-warning">{data.message}</div>;
  }
  if (data.status === "error") {
    return <div className="analysis-message analysis-error">{data.message}</div>;
  }

  const a = data.analysis;
  if (!a) return null;

  // Fallback: raw text
  if (a.raw_text) {
    return (
      <div className="analysis-raw">
        <pre>{a.raw_text}</pre>
      </div>
    );
  }

  return (
    <div className="analysis-structured">
      {/* Objet */}
      {a.objet && (
        <div className="analysis-block">
          <h4>🏗️ Objet</h4>
          <p>{a.objet}</p>
        </div>
      )}

      {/* Lots */}
      {a.lots && a.lots.length > 0 && (
        <div className="analysis-block">
          <h4>📦 Lots</h4>
          <ul>{a.lots.map((lot, i) => <li key={i}>{lot}</li>)}</ul>
        </div>
      )}

      {/* Critères d'attribution */}
      {a.criteres_attribution && a.criteres_attribution.length > 0 && (
        <div className="analysis-block">
          <h4>⚖️ Critères d'attribution</h4>
          <ul>{a.criteres_attribution.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}

      {/* Conditions de participation */}
      {a.conditions_participation && (
        <div className="analysis-block">
          <h4>📋 Conditions de participation</h4>
          <div className="analysis-conditions">
            {a.conditions_participation.capacite_technique && (
              <div className="condition-item">
                <span className="condition-label">Capacité technique</span>
                <span>{a.conditions_participation.capacite_technique}</span>
              </div>
            )}
            {a.conditions_participation.capacite_financiere && (
              <div className="condition-item">
                <span className="condition-label">Capacité financière</span>
                <span>{a.conditions_participation.capacite_financiere}</span>
              </div>
            )}
            {a.conditions_participation.agreations && a.conditions_participation.agreations.length > 0 && (
              <div className="condition-item">
                <span className="condition-label">Agréations</span>
                <span>{a.conditions_participation.agreations.join(", ")}</span>
              </div>
            )}
            {a.conditions_participation.certifications && a.conditions_participation.certifications.length > 0 && (
              <div className="condition-item">
                <span className="condition-label">Certifications</span>
                <span>{a.conditions_participation.certifications.join(", ")}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Budget */}
      {a.budget && (a.budget.valeur_estimee || a.budget.cautionnement) && (
        <div className="analysis-block">
          <h4>💰 Budget</h4>
          <div className="analysis-conditions">
            {a.budget.valeur_estimee && (
              <div className="condition-item">
                <span className="condition-label">Valeur estimée</span>
                <span>{a.budget.valeur_estimee}</span>
              </div>
            )}
            {a.budget.cautionnement && (
              <div className="condition-item">
                <span className="condition-label">Cautionnement</span>
                <span>{a.budget.cautionnement}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Calendrier */}
      {a.calendrier && (a.calendrier.date_limite || a.calendrier.duree_marche || a.calendrier.delai_execution || a.calendrier.visite_obligatoire) && (
        <div className="analysis-block">
          <h4>📅 Calendrier</h4>
          <div className="analysis-conditions">
            {a.calendrier.date_limite && (
              <div className="condition-item">
                <span className="condition-label">Date limite</span>
                <span>{a.calendrier.date_limite}</span>
              </div>
            )}
            {a.calendrier.duree_marche && (
              <div className="condition-item">
                <span className="condition-label">Durée du marché</span>
                <span>{a.calendrier.duree_marche}</span>
              </div>
            )}
            {a.calendrier.delai_execution && (
              <div className="condition-item">
                <span className="condition-label">Délai d'exécution</span>
                <span>{a.calendrier.delai_execution}</span>
              </div>
            )}
            {a.calendrier.visite_obligatoire && (
              <div className="condition-item">
                <span className="condition-label">Visite obligatoire</span>
                <span className="condition-highlight">{a.calendrier.visite_obligatoire}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Points d'attention */}
      {a.points_attention && a.points_attention.length > 0 && (
        <div className="analysis-block analysis-attention">
          <h4>⚠️ Points d'attention</h4>
          <ul>{a.points_attention.map((p, i) => <li key={i}>{p}</li>)}</ul>
        </div>
      )}

      {/* Score PME */}
      {a.score_accessibilite_pme && (
        <div className="analysis-block">
          <h4>🏢 Accessibilité PME</h4>
          <span
            className="pme-score-badge"
            style={{ background: PME_SCORE_COLORS[a.score_accessibilite_pme.split("—")[0].trim()] || "#6b7280" }}
          >
            {a.score_accessibilite_pme}
          </span>
        </div>
      )}

      {/* Meta */}
      {data.cached && (
        <div className="analysis-meta">
          <span className="ai-cached-badge">en cache</span>
        </div>
      )}
    </div>
  );
}

// ── Main Modal ──────────────────────────────────────────────────

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

  // Document Analysis state (per document)
  const [analysisResults, setAnalysisResults] = useState<Record<string, DocumentAnalysisResponse>>({});
  const [analysisLoading, setAnalysisLoading] = useState<Record<string, boolean>>({});
  const [analysisErrors, setAnalysisErrors] = useState<Record<string, string>>({});
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  // Q&A state
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaHistory, setQaHistory] = useState<Array<{ q: string; a: QAResponse }>>([]);
  const [qaLoading, setQaLoading] = useState(false);
  const [qaError, setQaError] = useState<string | null>(null);

  // Upload state
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [showUploadHelp, setShowUploadHelp] = useState(false);

  // Per-doc download state
  const [downloadLoading, setDownloadLoading] = useState<Record<string, boolean>>({});
  const [downloadMessages, setDownloadMessages] = useState<Record<string, string>>({});

  // BOSA document discovery state
  const [discoverLoading, setDiscoverLoading] = useState(false);
  const [discoverMessage, setDiscoverMessage] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setSummaryData(null);
    setSummaryError(null);
    setAnalysisResults({});
    setAnalysisErrors({});
    setExpandedDoc(null);
    setQaQuestion("");
    setQaHistory([]);
    setQaError(null);
    setUploadMessage(null);
    setDownloadLoading({});
    setDownloadMessages({});
    setDiscoverLoading(false);
    setDiscoverMessage(null);
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

  const handleAnalyzeDoc = async (docId: string, force = false) => {
    setAnalysisLoading((prev) => ({ ...prev, [docId]: true }));
    setAnalysisErrors((prev) => ({ ...prev, [docId]: "" }));
    setExpandedDoc(docId);
    try {
      const data = await analyzeDocument(noticeId, docId, summaryLang, force);
      setAnalysisResults((prev) => ({ ...prev, [docId]: data }));
    } catch (e) {
      setAnalysisErrors((prev) => ({
        ...prev,
        [docId]: e instanceof Error ? e.message : "Erreur lors de l'analyse",
      }));
    } finally {
      setAnalysisLoading((prev) => ({ ...prev, [docId]: false }));
    }
  };

  const toggleDocExpand = (docId: string) => {
    if (expandedDoc === docId) {
      setExpandedDoc(null);
    } else {
      setExpandedDoc(docId);
      // Auto-fetch cached analysis if not already loaded
      if (!analysisResults[docId] && !analysisLoading[docId]) {
        handleAnalyzeDoc(docId);
      }
    }
  };

  const handleAskQuestion = async () => {
    const q = qaQuestion.trim();
    if (!q || qaLoading) return;
    setQaLoading(true);
    setQaError(null);
    try {
      const result = await askNoticeQuestion(noticeId, q, summaryLang);
      setQaHistory((prev) => [...prev, { q, a: result }]);
      setQaQuestion("");
    } catch (e) {
      setQaError(e instanceof Error ? e.message : "Erreur lors de la requête");
    } finally {
      setQaLoading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadLoading(true);
    setUploadMessage(null);
    try {
      const result = await uploadDocument(noticeId, file);
      setUploadMessage(result.message);
      // Refresh docs list
      const d = await getNoticeDocuments(noticeId).catch(() => ({ items: [], total: 0 }));
      setDocs(d.items);
    } catch (err) {
      setUploadMessage(err instanceof Error ? err.message : "Erreur d'upload");
    } finally {
      setUploadLoading(false);
      e.target.value = ""; // reset input
    }
  };

  const handleDownloadDoc = async (docId: string) => {
    setDownloadLoading((prev) => ({ ...prev, [docId]: true }));
    setDownloadMessages((prev) => ({ ...prev, [docId]: "" }));
    try {
      const result = await downloadDocument(noticeId, docId);
      setDownloadMessages((prev) => ({ ...prev, [docId]: result.message }));
      // Refresh doc list to update download_status
      const d = await getNoticeDocuments(noticeId).catch(() => ({ items: [], total: 0 }));
      setDocs(d.items);
    } catch (err) {
      setDownloadMessages((prev) => ({
        ...prev,
        [docId]: err instanceof Error ? err.message : "Erreur de téléchargement",
      }));
    } finally {
      setDownloadLoading((prev) => ({ ...prev, [docId]: false }));
    }
  };

  const handleDiscover = async () => {
    setDiscoverLoading(true);
    setDiscoverMessage(null);
    try {
      const result = await discoverDocuments(noticeId);
      setDiscoverMessage(result.message);
      // Refresh docs list to show newly discovered PDFs
      const d = await getNoticeDocuments(noticeId).catch(() => ({ items: [], total: 0 }));
      setDocs(d.items);
    } catch (err) {
      setDiscoverMessage(err instanceof Error ? err.message : "Erreur lors de la découverte");
    } finally {
      setDiscoverLoading(false);
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
                  <span className="meta-label">NUTS</span>
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
            <div className="notice-section">
              <div className="docs-header">
                <h3>Documents ({docs.length})</h3>
                <div className="docs-header-actions">
                  {/* BOSA discover button */}
                  {notice.source?.toUpperCase().includes("BOSA") && (
                    <button
                      className={`btn-sm btn-discover ${discoverLoading ? "loading" : ""}`}
                      onClick={handleDiscover}
                      disabled={discoverLoading}
                      title="Récupérer les PDFs depuis l'espace BOSA"
                    >
                      {discoverLoading ? (
                        <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg> Chargement…</>
                      ) : (
                        <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Récupérer les PDFs</>
                      )}
                    </button>
                  )}
                  <label className={`btn-sm btn-outline btn-upload ${uploadLoading ? "loading" : ""}`}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                    </svg>
                    {uploadLoading ? "Upload…" : "Ajouter un PDF"}
                    <input type="file" accept=".pdf" onChange={handleUpload} disabled={uploadLoading} style={{ display: "none" }} />
                  </label>
                  <div className="upload-help-wrapper">
                    <button
                      className="btn-icon-xs help-trigger"
                      onClick={() => setShowUploadHelp(!showUploadHelp)}
                      title="Aide"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    </button>
                    {showUploadHelp && (
                      <div className="upload-help-tooltip">
                        Certains documents sont hébergés sur des plateformes protégées par une authentification.
                        Si le téléchargement automatique échoue, vous pouvez récupérer le document manuellement
                        puis l'ajouter ici pour bénéficier de l'analyse IA complète.
                      </div>
                    )}
                  </div>
                </div>
              </div>
              {uploadMessage && (
                <div className={`upload-message ${uploadMessage.includes("Erreur") || uploadMessage.includes("erreur") || uploadMessage.includes("Échec") ? "error" : "success"}`}>
                  {uploadMessage}
                </div>
              )}
              {discoverMessage && (
                <div className={`upload-message ${discoverMessage.includes("Erreur") || discoverMessage.includes("erreur") ? "error" : "success"}`}>
                  {discoverMessage}
                </div>
              )}
              {docs.length > 0 && (
                <div className="docs-list">
                  {docs.map((doc) => {
                    const isUploaded = doc.url?.startsWith("upload://");
                    const isDownloaded = doc.download_status === "ok";
                    const isHtml = (doc.file_type || "").toUpperCase() === "HTML";
                    const hasRealUrl = doc.url && !doc.url.startsWith("upload://");
                    // Show download for any doc with a real URL that hasn't been downloaded yet
                    // (skip HTML-only portal links)
                    const canDownload = hasRealUrl && !isDownloaded && !isHtml;
                    const downloadFailed = doc.download_status === "failed" || doc.download_status === "skipped";
                    // Show analyze for docs that have text available
                    const canAnalyze = isPdfDoc(doc) && (isDownloaded || isUploaded);

                    return (
                    <div key={doc.id} className="doc-wrapper">
                      <div className="doc-row">
                        <a
                          href={isUploaded ? undefined : doc.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`doc-item ${isUploaded ? "doc-uploaded" : ""}`}
                          onClick={isUploaded ? (e) => e.preventDefault() : undefined}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                          </svg>
                          <span>{doc.title || "Document"}</span>
                          {doc.file_type && <span className="doc-type">{doc.file_type}</span>}
                          {doc.language && <span className="doc-lang">{doc.language.toUpperCase()}</span>}
                          {isUploaded && <span className="doc-upload-badge">uploadé</span>}
                          {isDownloaded && <span className="doc-downloaded-badge">✓ chargé</span>}
                          {downloadFailed && <span className="doc-failed-badge">⚠ indisponible</span>}
                          {doc.has_ai_analysis && <span className="doc-analyzed-badge">✓ analysé</span>}
                        </a>
                        <div className="doc-actions">
                          {/* Download button */}
                          {canDownload && (
                            <button
                              className="btn-sm btn-download"
                              onClick={() => handleDownloadDoc(doc.id)}
                              disabled={downloadLoading[doc.id]}
                              title="Télécharger et extraire le texte"
                            >
                              {downloadLoading[doc.id] ? (
                                <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg></>
                              ) : (
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                                </svg>
                              )}
                            </button>
                          )}
                          {/* Analyze button */}
                          {canAnalyze && (
                          <button
                            className="btn-sm btn-analyze"
                            onClick={() => {
                              if (analysisResults[doc.id] || doc.has_ai_analysis) {
                                toggleDocExpand(doc.id);
                              } else {
                                handleAnalyzeDoc(doc.id);
                              }
                            }}
                            disabled={analysisLoading[doc.id]}
                            title="Analyser ce document avec l'IA"
                          >
                            {analysisLoading[doc.id] ? (
                              <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg> Analyse…</>
                            ) : analysisResults[doc.id] || doc.has_ai_analysis ? (
                              <>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                                  <polyline points="14 2 14 8 20 8"/>
                                  <line x1="16" y1="13" x2="8" y2="13"/>
                                  <line x1="16" y1="17" x2="8" y2="17"/>
                                </svg>
                                {expandedDoc === doc.id ? "Masquer" : "Voir l'analyse"}
                              </>
                            ) : (
                              <>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                                </svg>
                                Analyser
                              </>
                            )}
                          </button>
                        )}
                        </div>{/* /doc-actions */}
                      </div>{/* /doc-row */}

                      {/* Download status message */}
                      {downloadMessages[doc.id] && (
                        <div className={`doc-download-message ${doc.download_status === "ok" ? "success" : "info"}`}>
                          {downloadMessages[doc.id]}
                        </div>
                      )}

                      {/* Analysis result panel */}
                      {expandedDoc === doc.id && (
                        <div className="doc-analysis-panel">
                          {analysisLoading[doc.id] && (
                            <div className="analysis-loading">
                              <svg className="spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                              <span>Téléchargement et analyse du document en cours…</span>
                            </div>
                          )}
                          {analysisErrors[doc.id] && (
                            <div className="analysis-message analysis-error">{analysisErrors[doc.id]}</div>
                          )}
                          {analysisResults[doc.id] && !analysisLoading[doc.id] && (
                            <div className="analysis-result-container">
                              <div className="analysis-result-header">
                                <span>Analyse IA du document</span>
                                {analysisResults[doc.id].status === "ok" && (
                                  <button
                                    className="btn-xs btn-outline"
                                    onClick={() => handleAnalyzeDoc(doc.id, true)}
                                    title="Regénérer l'analyse"
                                  >
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
                                  </button>
                                )}
                              </div>
                              <AnalysisPanel data={analysisResults[doc.id]} />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Q&A Section */}
            <div className="notice-section notice-qa-section">
              <h3>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
                Questions sur ce marché
              </h3>
              <p className="qa-subtitle">
                Posez une question — l'IA analyse les documents et les données de l'avis pour y répondre.
              </p>

              {qaHistory.length > 0 && (
                <div className="qa-history">
                  {qaHistory.map((item, i) => (
                    <div key={i} className="qa-exchange">
                      <div className="qa-question-bubble">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        <span>{item.q}</span>
                      </div>
                      <div className={`qa-answer-bubble ${item.a.status !== "ok" ? "qa-answer-error" : ""}`}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 2a4 4 0 014 4c0 1.95-1.4 3.58-3.25 3.93L12 22"/>
                          <path d="M8 6a4 4 0 018 0"/>
                        </svg>
                        <div className="qa-answer-content">
                          {item.a.status === "ok" ? (
                            <>
                              <p>{item.a.answer}</p>
                              {item.a.sources && item.a.sources.length > 0 && (
                                <div className="qa-sources">
                                  Sources : {item.a.sources.map((s) => s.title).join(", ")}
                                </div>
                              )}
                            </>
                          ) : (
                            <p className="qa-no-answer">{item.a.message || "Pas de réponse disponible."}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {qaError && <div className="qa-error">{qaError}</div>}

              <div className="qa-input-row">
                <input
                  type="text"
                  className="qa-input"
                  placeholder="Ex : Quelles sont les conditions de participation ?"
                  value={qaQuestion}
                  onChange={(e) => setQaQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleAskQuestion(); }}
                  disabled={qaLoading}
                  maxLength={2000}
                />
                <button
                  className="btn-sm btn-ai qa-send-btn"
                  onClick={handleAskQuestion}
                  disabled={qaLoading || !qaQuestion.trim()}
                  title="Envoyer la question"
                >
                  {qaLoading ? (
                    <svg className="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                  )}
                </button>
              </div>
            </div>

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
