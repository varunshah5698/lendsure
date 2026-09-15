import "./Skeleton.css";

export default function Skeleton({ lines = 3, className = "" }) {
  return (
    <div className={`skeleton-group ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton" style={{ width: `${60 + Math.random() * 40}%` }} />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = "" }) {
  return (
    <div className={`skeleton-card ${className}`}>
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-text" />
      <div className="skeleton skeleton-text" style={{ width: "80%" }} />
      <div className="skeleton skeleton-bar" />
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 5 }) {
  return (
    <div className="skeleton-table">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="skeleton-row">
          {Array.from({ length: cols }).map((_, c) => (
            <div key={c} className="skeleton skeleton-cell" />
          ))}
        </div>
      ))}
    </div>
  );
}
