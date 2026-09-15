import "./kit.css";

export default function SegmentedControl({ options, value, onChange }) {
  return (
    <div className="kit-seg" role="tablist">
      {options.map((o) => {
        const v = typeof o === "string" ? o : o.value;
        const label = typeof o === "string" ? o : o.label;
        return (
          <button
            key={v} role="tab" aria-selected={value === v}
            className={`kit-seg-btn ${value === v ? "kit-seg-btn-active" : ""}`}
            onClick={() => onChange(v)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
