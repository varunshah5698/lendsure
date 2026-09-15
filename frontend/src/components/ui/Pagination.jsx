import "./kit.css";

export default function Pagination({ page, total, pageSize, onChange }) {
  const pages = Math.max(1, Math.ceil((total || 0) / (pageSize || 12)));
  if (pages <= 1) return null;
  const nums = [];
  for (let p = Math.max(1, page - 2); p <= Math.min(pages, page + 2); p++) nums.push(p);
  return (
    <div className="kit-pagination">
      <button className="kit-page-btn" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page">←</button>
      {nums[0] > 1 && <span className="kit-page-info">1 …</span>}
      {nums.map((p) => (
        <button key={p} className={`kit-page-btn ${p === page ? "kit-page-btn-active" : ""}`} onClick={() => onChange(p)}>{p}</button>
      ))}
      {nums[nums.length - 1] < pages && <span className="kit-page-info">… {pages}</span>}
      <button className="kit-page-btn" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Next page">→</button>
    </div>
  );
}
