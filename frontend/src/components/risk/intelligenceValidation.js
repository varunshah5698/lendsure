export const todayUTC = () => new Date().toISOString().slice(0, 10);

export function validateRecord(record, categories) {
  const parsed = new Date(`${record.date}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(record.date) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== record.date || record.date < "2000-01-01" || record.date > todayUTC()) throw new Error("Date must be a valid YYYY-MM-DD between 2000-01-01 and today (UTC).");
  if (!["in", "out"].includes(record.direction)) throw new Error("Direction must be in or out.");
  if (!/^\d+(?:\.\d{1,2})?$/.test(String(record.amount)) || !Number.isFinite(Number(record.amount)) || Number(record.amount) <= 0 || Number(record.amount) > 1e12) throw new Error("Amount must be positive, at most 1 trillion, with up to two decimal places.");
  if (record.category && !categories.includes(record.category)) throw new Error("Select a supported category.");
  if ((record.description || "").length > 240) throw new Error("Description must not exceed 240 characters.");
  if (record.balance != null && record.balance !== "" && (!/^-?\d+(?:\.\d{1,2})?$/.test(String(record.balance)) || Math.abs(Number(record.balance)) > 1e12)) throw new Error("Balance must be a signed decimal within ±1 trillion, with up to two decimal places.");
  return { ...record, amount: Number(record.amount), category: record.category || null, balance: record.balance == null || record.balance === "" ? null : Number(record.balance) };
}

export function validateExpiry(value) {
  const date = new Date(value);
  const delta = date.getTime() - Date.now();
  if (!Number.isFinite(delta) || delta <= 0 || delta > 30 * 86400000) throw new Error("Authorization expiry must be in the future and no more than 30 days away.");
  return date.toISOString();
}

export function validateStatement(text, categories) {
  if (new TextEncoder().encode(text).length > 1000000 || text.includes("\0")) throw new Error("CSV must be at most 1MB (1,000,000 bytes) and contain no null bytes.");
  const rows = [];
  let row = [], field = "", quoted = false, closed = false;
  const cell = () => { row.push(field); field = ""; closed = false; };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else field += c;
    } else if (c === '"') {
      if (field || closed) throw new Error("Malformed CSV quoting.");
      quoted = true;
    } else if (c === ",") cell();
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      cell(); rows.push(row); row = [];
    } else {
      if (closed) throw new Error("Unexpected text after a quoted CSV field.");
      field += c;
    }
  }
  if (quoted) throw new Error("Unclosed CSV quote.");
  if (field || row.length || closed) { cell(); rows.push(row); }
  const columns = ["date", "direction", "amount", "category", "description", "balance"];
  if (JSON.stringify(rows.shift()) !== JSON.stringify(columns)) throw new Error("CSV header must be exactly date,direction,amount,category,description,balance.");
  if (!rows.length || rows.length > 2000) throw new Error("CSV must contain 1–2000 records.");
  rows.forEach((values, i) => {
    if (values.length !== 6) throw new Error(`CSV row ${i + 2} must have exactly six columns.`);
    try { validateRecord(Object.fromEntries(columns.map((key, j) => [key, values[j]])), categories); }
    catch (error) { throw new Error(`CSV row ${i + 2}: ${error.message}`); }
  });
  return text;
}

export const activeConsent = (consent) => ["sandbox", "attested"].includes(consent.status) && new Date(consent.expires_at).getTime() > Date.now();
