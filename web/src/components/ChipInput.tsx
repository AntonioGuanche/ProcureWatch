import { useState, useRef } from "react";

interface ChipInputProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}

export function ChipInput({ label, values, onChange, placeholder }: ChipInputProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const addChip = (val: string) => {
    const trimmed = val.trim();
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed]);
    }
    setInput("");
  };

  const removeChip = (index: number) => {
    onChange(values.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addChip(input);
    }
    if (e.key === "Backspace" && input === "" && values.length > 0) {
      removeChip(values.length - 1);
    }
  };

  return (
    <div className="form-group">
      <label>{label}</label>
      <div
        className="chip-input-container"
        onClick={() => inputRef.current?.focus()}
      >
        {values.map((v, i) => (
          <span key={i} className="chip">
            {v}
            <button
              type="button"
              className="chip-remove"
              onClick={(e) => {
                e.stopPropagation();
                removeChip(i);
              }}
              aria-label={`Supprimer ${v}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => { if (input.trim()) addChip(input); }}
          placeholder={values.length === 0 ? placeholder : ""}
          className="chip-input"
        />
      </div>
    </div>
  );
}
