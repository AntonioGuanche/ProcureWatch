import { useState } from "react";
import type { WatchlistCreate, WatchlistUpdate, Watchlist } from "../types";

interface WatchlistFormProps {
  initial?: Watchlist | null;
  onSubmit: (payload: WatchlistCreate | WatchlistUpdate) => Promise<void>;
  onCancel?: () => void;
}

const emptyForm: WatchlistCreate = {
  name: "",
  is_enabled: true,
  term: null,
  cpv_prefix: null,
  buyer_contains: null,
  procedure_type: null,
  country: "BE",
  language: null,
  notify_email: null,
};

export function WatchlistForm({ initial, onSubmit, onCancel }: WatchlistFormProps) {
  const [form, setForm] = useState<WatchlistCreate | WatchlistUpdate>(() =>
    initial
      ? {
          name: initial.name,
          is_enabled: initial.is_enabled,
          term: initial.term ?? null,
          cpv_prefix: initial.cpv_prefix ?? null,
          buyer_contains: initial.buyer_contains ?? null,
          procedure_type: initial.procedure_type ?? null,
          country: initial.country,
          language: initial.language ?? null,
          notify_email: initial.notify_email ?? null,
        }
      : { ...emptyForm }
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (key: keyof WatchlistCreate, value: string | boolean | null) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name?.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSubmit(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="wl-form">
      {error && <div className="alert alert-error">{error}</div>}

      <div className="form-group">
        <label>Nom *</label>
        <input
          value={form.name ?? ""}
          onChange={(e) => update("name", e.target.value)}
          required
          placeholder="ex: Travaux construction BE"
        />
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.is_enabled ?? true}
            onChange={(e) => update("is_enabled", e.target.checked)}
          />
          Activée
        </label>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Mots-clés</label>
          <input
            value={form.term ?? ""}
            onChange={(e) => update("term", e.target.value || null)}
            placeholder="ex: construction, nettoyage"
          />
        </div>
        <div className="form-group">
          <label>Préfixe CPV</label>
          <input
            value={form.cpv_prefix ?? ""}
            onChange={(e) => update("cpv_prefix", e.target.value || null)}
            placeholder="ex: 45"
          />
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Acheteur contient</label>
          <input
            value={form.buyer_contains ?? ""}
            onChange={(e) => update("buyer_contains", e.target.value || null)}
            placeholder="Nom de l'organisme"
          />
        </div>
        <div className="form-group">
          <label>Type de procédure</label>
          <input
            value={form.procedure_type ?? ""}
            onChange={(e) => update("procedure_type", e.target.value || null)}
            placeholder="ex: open, restricted"
          />
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Pays</label>
          <input
            value={form.country ?? "BE"}
            onChange={(e) => update("country", e.target.value || "BE")}
          />
        </div>
        <div className="form-group">
          <label>Langue</label>
          <input
            value={form.language ?? ""}
            onChange={(e) => update("language", e.target.value || null)}
            placeholder="ex: FR, NL"
          />
        </div>
      </div>

      <div className="form-group">
        <label>Email de notification</label>
        <input
          type="email"
          value={form.notify_email ?? ""}
          onChange={(e) => update("notify_email", e.target.value || null)}
          placeholder="votre@email.com"
        />
      </div>

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Enregistrement…" : initial ? "Mettre à jour" : "Créer la veille"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Annuler
          </button>
        )}
      </div>
    </form>
  );
}
