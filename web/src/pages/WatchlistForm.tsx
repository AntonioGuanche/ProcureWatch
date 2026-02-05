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

  const update = (key: keyof WatchlistCreate, value: string | boolean | null) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name?.trim()) return;
    setSaving(true);
    try {
      await onSubmit(form);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label>Name *</label>
        <input
          value={form.name ?? ""}
          onChange={(e) => update("name", e.target.value)}
          required
          placeholder="e.g. Travaux BE"
        />
      </div>
      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={form.is_enabled ?? true}
            onChange={(e) => update("is_enabled", e.target.checked)}
          />{" "}
          Enabled
        </label>
      </div>
      <div className="form-group">
        <label>Term</label>
        <input
          value={form.term ?? ""}
          onChange={(e) => update("term", e.target.value || null)}
          placeholder="Search term in title"
        />
      </div>
      <div className="form-group">
        <label>CPV prefix</label>
        <input
          value={form.cpv_prefix ?? ""}
          onChange={(e) => update("cpv_prefix", e.target.value || null)}
          placeholder="e.g. 45"
        />
      </div>
      <div className="form-group">
        <label>Buyer contains</label>
        <input
          value={form.buyer_contains ?? ""}
          onChange={(e) => update("buyer_contains", e.target.value || null)}
        />
      </div>
      <div className="form-group">
        <label>Procedure type</label>
        <input
          value={form.procedure_type ?? ""}
          onChange={(e) => update("procedure_type", e.target.value || null)}
        />
      </div>
      <div className="form-group">
        <label>Country</label>
        <input
          value={form.country ?? "BE"}
          onChange={(e) => update("country", e.target.value || "BE")}
        />
      </div>
      <div className="form-group">
        <label>Language</label>
        <input
          value={form.language ?? ""}
          onChange={(e) => update("language", e.target.value || null)}
        />
      </div>
      <div className="form-group">
        <label>Notify email</label>
        <input
          type="email"
          value={form.notify_email ?? ""}
          onChange={(e) => update("notify_email", e.target.value || null)}
          placeholder="Digest recipient"
        />
      </div>
      <div style={{ marginTop: "1rem" }}>
        <button type="submit" className="btn primary" disabled={saving}>
          {saving ? "Saving…" : initial ? "Update" : "Create"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn">
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
