import { useState } from "react";
import type { WatchlistCreate, WatchlistUpdate, Watchlist } from "../types";
import { ChipInput } from "../components/ChipInput";
import { useAuth } from "../auth";

interface WatchlistFormProps {
  initial?: Watchlist | null;
  onSubmit: (payload: WatchlistCreate | WatchlistUpdate) => Promise<void>;
  onCancel?: () => void;
}

export function WatchlistForm({ initial, onSubmit, onCancel }: WatchlistFormProps) {
  const { user } = useAuth();
  const [name, setName] = useState(initial?.name ?? "");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [keywords, setKeywords] = useState<string[]>(initial?.keywords ?? []);
  const [cpvPrefixes, setCpvPrefixes] = useState<string[]>(initial?.cpv_prefixes ?? []);
  const [countries, setCountries] = useState<string[]>(initial?.countries ?? []);
  const [nutsPrefixes, setNutsPrefixes] = useState<string[]>(initial?.nuts_prefixes ?? []);
  const [notifyEmail, setNotifyEmail] = useState(initial?.notify_email ?? user?.email ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);

    const payload: WatchlistCreate | WatchlistUpdate = {
      name: name.trim(),
      enabled,
      keywords,
      cpv_prefixes: cpvPrefixes,
      countries,
      nuts_prefixes: nutsPrefixes,
      notify_email: notifyEmail.trim() || null,
    };

    try {
      await onSubmit(payload);
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
        <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="ex: Travaux construction BE" />
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Activée
        </label>
      </div>

      <div className="form-row">
        <ChipInput label="Mots-clés" values={keywords} onChange={setKeywords} placeholder="Tapez puis Entrée (ex: construction)" />
        <ChipInput label="Préfixes CPV" values={cpvPrefixes} onChange={setCpvPrefixes} placeholder="ex: 45, 72" />
      </div>

      <div className="form-row">
        <ChipInput label="Pays (ISO2)" values={countries} onChange={setCountries} placeholder="ex: BE, FR" />
        <ChipInput label="Préfixes NUTS" values={nutsPrefixes} onChange={setNutsPrefixes} placeholder="ex: BE1, BE100" />
      </div>

      <div className="form-group">
        <label>Email de notification</label>
        <input type="email" value={notifyEmail} onChange={(e) => setNotifyEmail(e.target.value)} placeholder="votre@email.com" />
      </div>

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Enregistrement…" : initial ? "Mettre à jour" : "Créer la veille"}
        </button>
        {onCancel && <button type="button" onClick={onCancel}>Annuler</button>}
      </div>
    </form>
  );
}
