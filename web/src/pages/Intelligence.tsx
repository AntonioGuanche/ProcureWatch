import { useEffect, useState, useCallback } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getCpvGroups, getCpvAnalysis } from "../api";
import { NoticeModal } from "../components/NoticeModal";
import type {
  CpvGroupOption, CpvAnalysisResponse,
  CpvWinner, CpvBuyer, ActiveOpportunity, SingleBidContract,
} from "../types";

/* ── Helpers ─────────────────────────────────────────────────────── */

const COLORS = [
  "#3b5bdb", "#2b8a3e", "#e67700", "#c92a2a", "#7048e8",
  "#0c8599", "#d6336c", "#5c940d", "#862e9c", "#1864ab",
];

function eur(v: number | null | undefined): string {
  if (v == null || v === 0) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M€`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K€`;
  return `${v.toFixed(0)}€`;
}

function deadlineDays(d: number | null): string {
  if (d == null) return "—";
  if (d < 1) return "< 1j";
  return `${Math.round(d)}j`;
}

/* ── Section wrapper ─────────────────────────────────────────────── */

function Section({ title, icon, children, className = "" }: {
  title: string; icon: string; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={`intel-section ${className}`}>
      <h3 className="intel-section-title"><span>{icon}</span> {title}</h3>
      {children}
    </div>
  );
}

/* ── Main component ──────────────────────────────────────────────── */

export function Intelligence() {
  const [groups, setGroups] = useState<CpvGroupOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [months, setMonths] = useState(24);
  const [data, setData] = useState<CpvAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedNoticeId, setSelectedNoticeId] = useState<string | null>(null);

  // Load CPV groups on mount
  useEffect(() => {
    getCpvGroups()
      .then((r) => setGroups(r.groups))
      .catch(() => setError("Impossible de charger les groupes CPV"));
  }, []);

  const analyze = useCallback(() => {
    if (selected.length === 0) return;
    setLoading(true);
    setError(null);
    getCpvAnalysis(selected, months)
      .then(setData)
      .catch((e) => setError(e?.message || "Erreur d'analyse"))
      .finally(() => setLoading(false));
  }, [selected, months]);

  const toggleCpv = (code: string) => {
    setSelected((prev) =>
      prev.includes(code)
        ? prev.filter((c) => c !== code)
        : prev.length < 10
        ? [...prev, code]
        : prev
    );
  };

  const filtered = groups.filter(
    (g) =>
      g.code.includes(search) ||
      g.label.toLowerCase().includes(search.toLowerCase())
  );

  const d = data; // alias for convenience

  return (
    <div className="intel-page">
      <div className="intel-header">
        <h1>Intelligence sectorielle</h1>
        <p className="page-subtitle">
          Analysez en profondeur les marchés publics par secteur CPV
        </p>
      </div>

      {/* ── CPV selector ────────────────────────────────────────────── */}
      <div className="intel-controls">
        <div className="intel-cpv-selector">
          <label>Secteurs CPV (max 10)</label>
          <input
            type="text"
            placeholder="Rechercher un code ou un secteur…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input"
          />
          {selected.length > 0 && (
            <div className="intel-selected-chips">
              {selected.map((code) => {
                const g = groups.find((x) => x.code === code);
                return (
                  <span key={code} className="chip chip-active" onClick={() => toggleCpv(code)}>
                    {code} — {g?.label || "?"} ×
                  </span>
                );
              })}
            </div>
          )}
          <div className="intel-cpv-list">
            {filtered.slice(0, 30).map((g) => (
              <button
                key={g.code}
                className={`intel-cpv-item ${selected.includes(g.code) ? "selected" : ""}`}
                onClick={() => toggleCpv(g.code)}
              >
                <span className="cpv-code">{g.code}</span>
                <span className="cpv-label">{g.label}</span>
                {g.count != null && <span className="cpv-count">{g.count.toLocaleString("fr-BE")}</span>}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="intel-cpv-empty">Aucun résultat</div>
            )}
          </div>
        </div>

        <div className="intel-period">
          <label>Période</label>
          <select value={months} onChange={(e) => setMonths(+e.target.value)} className="input">
            <option value={12}>12 mois</option>
            <option value={24}>24 mois</option>
            <option value={36}>3 ans</option>
            <option value={60}>5 ans</option>
          </select>
          <button
            className="btn btn-primary"
            onClick={analyze}
            disabled={loading || selected.length === 0}
          >
            {loading ? "Analyse en cours…" : "Analyser"}
          </button>
        </div>
      </div>

      {error && <div className="intel-error">{error}</div>}

      {loading && (
        <div className="intel-loading">
          <div className="spinner" />
          <span>Analyse de {selected.length} secteur{selected.length > 1 ? "s" : ""} sur {months} mois…</span>
        </div>
      )}

      {/* ── Results ─────────────────────────────────────────────────── */}
      {d && !loading && (
        <div className="intel-results">

          {/* ── 1. Volume & Valeur ──────────────────────────────────── */}
          <Section title="Volume & Valeur" icon="📊">
            <div className="intel-kpi-row">
              <div className="kpi-card">
                <div className="kpi-value">{d.volume_value.totals.total_notices.toLocaleString("fr-BE")}</div>
                <div className="kpi-label">Marchés publiés</div>
              </div>
              <div className="kpi-card accent">
                <div className="kpi-value">{d.volume_value.totals.total_awarded.toLocaleString("fr-BE")}</div>
                <div className="kpi-label">Marchés attribués</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-value">{eur(d.volume_value.totals.sum_estimated_eur)}</div>
                <div className="kpi-label">Valeur estimée totale</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-value">{eur(d.volume_value.totals.sum_awarded_eur)}</div>
                <div className="kpi-label">Valeur attribuée totale</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-value">{eur(d.volume_value.totals.avg_estimated_eur)}</div>
                <div className="kpi-label">Valeur moy. estimée</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-value">{eur(d.volume_value.totals.avg_awarded_eur)}</div>
                <div className="kpi-label">Valeur moy. attribuée</div>
              </div>
            </div>

            {d.volume_value.monthly.length > 0 && (
              <div className="intel-chart-wrap">
                <h4>Publications par mois</h4>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={d.volume_value.monthly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} interval={Math.max(0, Math.floor(d.volume_value.monthly.length / 12) - 1)} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: number) => v.toLocaleString("fr-BE")} />
                    <Bar dataKey="count" fill="#3b5bdb" name="Publiés" radius={[2, 2, 0, 0]} />
                    <Bar dataKey="awarded" fill="#2b8a3e" name="Attribués" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {d.volume_value.yearly.length > 0 && (
              <div className="intel-chart-wrap">
                <h4>Évolution annuelle</h4>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={d.volume_value.yearly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
                    <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: number) => v.toLocaleString("fr-BE")} />
                    <Legend />
                    <Line type="monotone" dataKey="count" stroke="#3b5bdb" strokeWidth={2} name="Publiés" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="awarded" stroke="#2b8a3e" strokeWidth={2} name="Attribués" dot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Section>

          {/* ── 2. Top entreprises ──────────────────────────────────── */}
          <Section title="Top entreprises du secteur" icon="🏢">
            {d.top_winners.length > 0 ? (
              <div className="intel-table-wrap">
                <table className="intel-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Entreprise</th>
                      <th>Contrats</th>
                      <th>Valeur totale</th>
                      <th>Valeur moy.</th>
                      <th>Dernier contrat</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.top_winners.map((w: CpvWinner, i: number) => (
                      <tr key={w.name}>
                        <td className="rank">{i + 1}</td>
                        <td className="name">{w.name}</td>
                        <td>{w.contracts_won}</td>
                        <td>{eur(w.total_value_eur)}</td>
                        <td>{eur(w.avg_value_eur)}</td>
                        <td>{w.last_award || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="intel-empty">Aucune attribution trouvée</p>}
          </Section>

          {/* ── 3. Top pouvoirs adjudicateurs ──────────────────────── */}
          <Section title="Top pouvoirs adjudicateurs" icon="🏛️">
            {d.top_buyers.length > 0 ? (
              <div className="intel-table-wrap">
                <table className="intel-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Autorité</th>
                      <th>Marchés</th>
                      <th>Attribués</th>
                      <th>Valeur estimée</th>
                      <th>Valeur attribuée</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.top_buyers.map((b: CpvBuyer, i: number) => (
                      <tr key={b.name}>
                        <td className="rank">{i + 1}</td>
                        <td className="name">{b.name}</td>
                        <td>{b.notice_count}</td>
                        <td>{b.awarded_count}</td>
                        <td>{eur(b.total_estimated_eur)}</td>
                        <td>{eur(b.total_awarded_eur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="intel-empty">Aucune donnée disponible</p>}
          </Section>

          {/* ── 4. Concurrence ─────────────────────────────────────── */}
          <Section title="Niveau de concurrence" icon="⚔️">
            <div className="intel-kpi-row small">
              <div className="kpi-card">
                <div className="kpi-value">{d.competition.avg_tenders}</div>
                <div className="kpi-label">Offres en moyenne</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-value">{d.competition.median_tenders}</div>
                <div className="kpi-label">Médiane</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-value">{d.competition.total_with_data.toLocaleString("fr-BE")}</div>
                <div className="kpi-label">Marchés avec données</div>
              </div>
            </div>
            {d.competition.distribution.length > 0 && (
              <div className="intel-chart-wrap">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={d.competition.distribution} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="label" width={160} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: number, _: string, p: any) => [`${v} (${p.payload.pct}%)`, "Marchés"]} />
                    <Bar dataKey="count" fill="#3b5bdb" radius={[0, 4, 4, 0]}>
                      {d.competition.distribution.map((_: any, i: number) => (
                        <Cell key={i} fill={i === 0 ? "#2b8a3e" : COLORS[i % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Section>

          {/* ── 5. Types de procédures ─────────────────────────────── */}
          <Section title="Types de procédures" icon="📋" className="intel-half">
            {d.procedure_types.length > 0 && (
              <div className="intel-chart-wrap">
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={d.procedure_types.slice(0, 8)}
                      dataKey="count"
                      nameKey="type"
                      cx="50%" cy="50%"
                      outerRadius={100}
                      label={({ type, pct }: any) => `${type} (${pct}%)`}
                      labelLine={false}
                    >
                      {d.procedure_types.slice(0, 8).map((_: any, i: number) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number, _: string, p: any) => [`${v} (${p.payload.pct}%)`, p.payload.type]} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </Section>

          {/* ── 6. Géographie ──────────────────────────────────────── */}
          <Section title="Répartition géographique" icon="🗺️" className="intel-half">
            {d.geography.length > 0 ? (
              <div className="intel-table-wrap compact">
                <table className="intel-table">
                  <thead>
                    <tr><th>Région</th><th>Code</th><th>Marchés</th></tr>
                  </thead>
                  <tbody>
                    {d.geography.slice(0, 15).map((g) => (
                      <tr key={g.nuts_code}>
                        <td>{g.label}</td>
                        <td className="code">{g.nuts_code}</td>
                        <td>{g.count.toLocaleString("fr-BE")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="intel-empty">Aucune donnée géographique</p>}
          </Section>

          {/* ── 7. Saisonnalité ────────────────────────────────────── */}
          <Section title="Saisonnalité" icon="📅">
            {d.seasonality.length > 0 && (
              <div className="intel-chart-wrap">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={d.seasonality}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
                    <XAxis dataKey="month_name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: number) => [v.toFixed(1), "Moy/an"]} />
                    <Bar dataKey="avg_per_year" fill="#7048e8" name="Moy. publications/an" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Section>

          {/* ── 8. Distribution des montants ────────────────────────── */}
          <Section title="Distribution des montants" icon="💰">
            <div className="intel-distrib-grid">
              {d.value_distribution.estimated.total_with_value > 0 && (
                <div className="intel-chart-wrap">
                  <h4>Valeurs estimées ({d.value_distribution.estimated.total_with_value} marchés)</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={d.value_distribution.estimated.buckets}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v: number, _: string, p: any) => [`${v} (${p.payload.pct}%)`, "Marchés"]} />
                      <Bar dataKey="count" fill="#3b5bdb" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              {d.value_distribution.awarded.total_with_value > 0 && (
                <div className="intel-chart-wrap">
                  <h4>Valeurs attribuées ({d.value_distribution.awarded.total_with_value} marchés)</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={d.value_distribution.awarded.buckets}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v: number, _: string, p: any) => [`${v} (${p.payload.pct}%)`, "Marchés"]} />
                      <Bar dataKey="count" fill="#2b8a3e" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </Section>

          {/* ── 9. Marchés sans concurrence ──────────────────────────── */}
          <Section title="Marchés sans concurrence (1 offre)" icon="🎯">
            <p className="intel-insight">
              <strong>{d.single_bid_contracts.total_single_bid}</strong> marchés attribués avec une seule offre dans ce secteur — signal d'opportunité pour les nouveaux entrants.
            </p>
            {d.single_bid_contracts.recent.length > 0 && (
              <div className="intel-table-wrap">
                <table className="intel-table clickable">
                  <thead>
                    <tr>
                      <th>Marché</th>
                      <th>Adjudicataire</th>
                      <th>Montant</th>
                      <th>Date</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.single_bid_contracts.recent.map((c: SingleBidContract) => (
                      <tr key={c.id} onClick={() => setSelectedNoticeId(c.id)}>
                        <td className="name">{c.title}</td>
                        <td>{c.winner}</td>
                        <td>{eur(c.award_value_eur ?? c.estimated_value_eur)}</td>
                        <td>{c.award_date || "—"}</td>
                        <td><span className={`tag tag-${c.source === "BOSA_EPROC" ? "bosa" : "ted"}`}>{c.source === "BOSA_EPROC" ? "BOSA" : "TED"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* ── 10. Délai d'attribution ──────────────────────────────── */}
          <Section title="Délai d'attribution" icon="⏱️" className="intel-half">
            {d.award_timeline.total_with_data > 0 ? (
              <div className="intel-kpi-row small">
                <div className="kpi-card">
                  <div className="kpi-value">{d.award_timeline.avg_days ?? "—"}<small>j</small></div>
                  <div className="kpi-label">Délai moyen</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-value">{d.award_timeline.median_days ?? "—"}<small>j</small></div>
                  <div className="kpi-label">Délai médian</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-value">{d.award_timeline.p25_days ?? "—"} — {d.award_timeline.p75_days ?? "—"}<small>j</small></div>
                  <div className="kpi-label">Intervalle 25-75%</div>
                </div>
              </div>
            ) : <p className="intel-empty">Pas assez de données</p>}
            <p className="intel-footnote">
              Basé sur {d.award_timeline.total_with_data} marchés avec dates de publication et d'attribution.
            </p>
          </Section>

          {/* ── 11. Opportunités en cours ────────────────────────────── */}
          <Section title="Opportunités en cours" icon="🚀" className="intel-half">
            <p className="intel-insight">
              <strong>{d.active_opportunities.total_active}</strong> marchés ouverts dans {selected.length > 1 ? "ces secteurs" : "ce secteur"}.
            </p>
            {d.active_opportunities.notices.length > 0 && (
              <div className="intel-table-wrap">
                <table className="intel-table clickable">
                  <thead>
                    <tr>
                      <th>Marché</th>
                      <th>Acheteur</th>
                      <th>Valeur est.</th>
                      <th>Reste</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.active_opportunities.notices.map((n: ActiveOpportunity) => (
                      <tr key={n.id} onClick={() => setSelectedNoticeId(n.id)}>
                        <td className="name">{n.title}</td>
                        <td>{n.buyer || "—"}</td>
                        <td>{eur(n.estimated_value_eur)}</td>
                        <td>
                          <span className={`tag ${(n.days_left ?? 999) <= 7 ? "tag-danger" : (n.days_left ?? 999) <= 14 ? "tag-warning" : "tag-default"}`}>
                            {deadlineDays(n.days_left)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

        </div>
      )}

      {/* Notice modal */}
      {selectedNoticeId && (
        <NoticeModal
          noticeId={selectedNoticeId}
          onClose={() => setSelectedNoticeId(null)}
          isFavorited={false}
          onToggleFavorite={() => {}}
        />
      )}
    </div>
  );
}
