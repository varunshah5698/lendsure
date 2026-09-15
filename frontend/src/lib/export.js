function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadCSV(filename, rows) {
  if (!rows?.length) return false;
  const cols = Object.keys(rows[0]);
  const esc = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  download(filename, csv, "text/csv;charset=utf-8");
  return true;
}

export function downloadJSON(filename, data) {
  download(filename, JSON.stringify(data, null, 2), "application/json");
  return true;
}
