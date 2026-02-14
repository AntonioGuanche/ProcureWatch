import { useState, useRef, useEffect, useCallback } from "react";

interface Option {
  code: string;
  label: string;
}

interface SearchableChipSelectProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  fetchOptions: (query: string) => Promise<Option[]>;
  placeholder?: string;
}

export function SearchableChipSelect({
  label,
  values,
  onChange,
  fetchOptions,
  placeholder,
}: SearchableChipSelectProps) {
  const [input, setInput] = useState("");
  const [options, setOptions] = useState<Option[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  // Fetch initial options on focus (empty query)
  const handleFocus = useCallback(() => {
    setShowDropdown(true);
    if (options.length === 0 && !input) {
      setLoading(true);
      fetchOptions("").then(setOptions).catch(() => {}).finally(() => setLoading(false));
    }
  }, [fetchOptions, options.length, input]);

  // Debounced search
  useEffect(() => {
    clearTimeout(timerRef.current);
    if (!showDropdown) return;
    timerRef.current = setTimeout(() => {
      setLoading(true);
      fetchOptions(input)
        .then((opts) => {
          setOptions(opts);
          setHighlightIndex(-1);
        })
        .catch(() => setOptions([]))
        .finally(() => setLoading(false));
    }, input ? 250 : 0);
    return () => clearTimeout(timerRef.current);
  }, [input, fetchOptions, showDropdown]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const addValue = (code: string) => {
    const val = code;
    if (!values.includes(val)) {
      onChange([...values, val]);
    }
    setInput("");
    setShowDropdown(false);
    inputRef.current?.focus();
  };

  const removeChip = (index: number) => {
    onChange(values.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((prev) => Math.min(prev + 1, filteredOptions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightIndex >= 0 && highlightIndex < filteredOptions.length) {
        addValue(filteredOptions[highlightIndex].code);
      }
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    } else if (e.key === "Backspace" && input === "" && values.length > 0) {
      removeChip(values.length - 1);
    }
  };

  // Filter out already-selected options
  const filteredOptions = options.filter((o) => {
    const code = o.code;
    return !values.includes(code);
  });

  // Resolve labels for current chips
  const chipLabel = useCallback(
    (code: string) => {
      const match = options.find((o) => {
        const oCode = o.code;
        return oCode === code;
      });
      return match ? `${code} — ${match.label}` : code;
    },
    [options],
  );

  return (
    <div className="form-group" ref={containerRef} style={{ position: "relative" }}>
      <label>{label}</label>
      <div
        className="chip-input-container"
        onClick={() => { inputRef.current?.focus(); handleFocus(); }}
      >
        {values.map((v, i) => (
          <span key={i} className="chip">
            {chipLabel(v)}
            <button
              type="button"
              className="chip-remove"
              onClick={(e) => { e.stopPropagation(); removeChip(i); }}
              aria-label={`Supprimer ${v}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => { setInput(e.target.value); setShowDropdown(true); }}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder={values.length === 0 ? placeholder : "Rechercher…"}
          className="chip-input"
          autoComplete="off"
        />
      </div>
      {showDropdown && (
        <div className="chip-dropdown">
          {loading && <div className="chip-dropdown-item chip-dropdown-loading">Recherche…</div>}
          {!loading && filteredOptions.length === 0 && (
            <div className="chip-dropdown-item chip-dropdown-empty">Aucun résultat</div>
          )}
          {!loading &&
            filteredOptions.map((opt, i) => (
              <div
                key={opt.code}
                className={`chip-dropdown-item ${i === highlightIndex ? "highlighted" : ""}`}
                onMouseDown={(e) => { e.preventDefault(); addValue(opt.code); }}
                onMouseEnter={() => setHighlightIndex(i)}
              >
                <span className="chip-dropdown-code">{opt.code}</span>
                <span className="chip-dropdown-label">{opt.label}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
