import { useState } from "react";
import Button from "../ui/Button";
import Badge from "../ui/Badge";
import { SignalCard } from "./IntelligenceShared";
import { activeConsent, todayUTC, validateExpiry, validateRecord, validateStatement } from "./intelligenceValidation";

function ConsentSelect({ consents, value, onChange, title }) {
  return <label>{title}<select className="filter-select" required value={value} onChange={e => onChange(e.target.value)}><option value="">Choose an active authorization</option>{consents.filter(activeConsent).map(c => <option key={c.id} value={c.id}>{c.scope} · {c.mode} · expires {c.expires_at} · {c.id.slice(0, 8)}</option>)}</select></label>;
}

export default function IntelligenceControls({ data, bid, scope, busy, run }) {
  const [mode, setMode] = useState("attested");
  const [agreed, setAgreed] = useState(false);
  const [expiry, setExpiry] = useState("");
  const [collectionConsent, setCollectionConsent] = useState("");
  const [declaredConsent, setDeclaredConsent] = useState("");
  const [record, setRecord] = useState({ date: "", direction: "in", amount: "", category: "", description: "" });
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const providers = data.providers || {};
  const sandbox = data.access?.granted === true && data.access?.demo_only === true && bid.startsWith("DEMO-") && providers.demo_enabled === true;
  const canCredit = sandbox && providers.credit?.sandbox_available === true;
  const canDemo = sandbox && providers.cashflow_demo_available === true;
  const canUpload = sandbox && providers.statement_upload_enabled === true;
  const canSandbox = scope === "credit" ? canCredit : canDemo || canUpload;
  const selectedMode = scope === "credit" ? "sandbox" : canSandbox ? mode : "attested";
  const consents = (data.consents || []).filter(c => c.scope === scope);
  const sandboxConsents = consents.filter(c => c.mode === "sandbox");
  const declaredConsents = consents.filter(c => c.mode === "attested");
  const categories = data.access?.categories || [];
  const validSelection = (id, mode) => consents.some(c => c.id === id && c.mode === mode && activeConsent(c));
  const submit = async (event, action) => {
    event.preventDefault();
    if (busy) return;
    setError("");
    try { await action(); } catch (e) { setError(e.message); }
  };
  const update = (key) => e => setRecord(r => ({ ...r, [key]: e.target.value }));
  return <div className="bi-stack">
    <SignalCard title={scope === "credit" ? "Credit sandbox agreement" : "Cashflow authorization"} sandbox={sandbox} description="Access grants are provisioned only by an authorized operator. Agreements and attestations do not grant access or establish verified legal consent.">
      {(scope !== "credit" || canCredit) ? <form onSubmit={e => submit(e, async () => {
        if (!agreed) throw new Error("Explicit acknowledgement is required.");
        const payload = { scope, mode: selectedMode, acknowledged: true };
        if (selectedMode === "attested") { payload.purpose = "cashflow_assessment"; payload.expires_at = validateExpiry(expiry); }
        else if (expiry) payload.expires_at = validateExpiry(expiry);
        if (await run("consent", payload)) { setAgreed(false); setExpiry(""); }
      })}>
        <fieldset disabled={busy} className="bi-form">
          {scope === "cashflow" && <label>Mode<select className="filter-select" value={selectedMode} onChange={e => { setMode(e.target.value); setAgreed(false); }}><option value="attested">Lender attestation · declared records</option>{canSandbox && <option value="sandbox">Fictional sandbox agreement</option>}</select></label>}
          <p>{selectedMode === "sandbox" ? "Fictional development data only. This agreement is not legal borrower consent, bureau consent, or bank consent. Default expiry: 24 hours." : "Purpose: cashflow_assessment. Record only borrower-declared income/expenses for which you hold recorded borrower authorization. This is a lender attestation, not verified legal consent or bureau/bank-provider consent."}</p>
          <label>Expires at (your local time; sent as ISO UTC){selectedMode === "sandbox" && " · optional"}<input className="filter-search-input" type="datetime-local" required={selectedMode === "attested"} value={expiry} onChange={e => setExpiry(e.target.value)} /></label>
          <small>Must be in the future and within 30 days.</small>
          <label className="bi-check"><input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} required />{selectedMode === "sandbox" ? "I explicitly agree to this fictional sandbox demonstration, not a real borrower assessment." : "I attest that recorded borrower authorization exists for this declared cashflow assessment and the stated expiry."}</label>
          <Button type="submit" disabled={busy || !agreed}>{busy ? "Working…" : selectedMode === "sandbox" ? "Record sandbox agreement" : "Record lender attestation"}</Button>
        </fieldset>
      </form> : <p>Sandbox credit collection unavailable. TransUnion is not connected. Contact an authorized operator; there is no self-grant action.</p>}
      {error && <p role="alert" className="bi-error">{error}</p>}
      <h4>Recorded agreements / attestations</h4>
      {consents.length ? <ul className="bi-consents">{consents.map(c => <li key={c.id}><div><Badge variant={c.mode === "sandbox" ? "warning" : "info"}>{c.mode === "sandbox" ? "SANDBOX" : "LENDER ATTESTATION"}</Badge><b>{c.scope} · {activeConsent(c) ? c.status : c.status === "revoked" ? "revoked" : "expired"}</b><p>{c.notice}</p><small>Created {c.created_at} · expires {c.expires_at} · purpose {c.purpose}</small></div>{activeConsent(c) && <Button type="button" variant="secondary" size="sm" disabled={busy} onClick={() => run("revoke", c.id)}>Revoke</Button>}</li>)}</ul> : <p>No agreements or attestations recorded for this scope.</p>}
    </SignalCard>
    {canSandbox && <SignalCard title="Development sandbox collection" sandbox description="Only this fictional DEMO- borrower and its explicitly provisioned demo-only grant are eligible. No live provider is connected.">
      <fieldset disabled={busy} className="bi-form">
        <ConsentSelect title="Sandbox agreement" consents={sandboxConsents} value={collectionConsent} onChange={setCollectionConsent} />
        {scope === "credit" && canCredit && <Button type="button" disabled={busy || !validSelection(collectionConsent, "sandbox")} onClick={() => run("fetchCredit", collectionConsent)}>Fetch fictional credit report</Button>}
        {scope === "cashflow" && canDemo && <Button type="button" disabled={busy || !validSelection(collectionConsent, "sandbox")} onClick={() => run("demo", collectionConsent)}>Load fictional cashflow</Button>}
        {scope === "cashflow" && canUpload && <form onSubmit={e => submit(e, async () => {
          if (!file || file.size > 1000000 || !file.name.toLowerCase().endsWith(".csv")) throw new Error("Choose a CSV file no larger than 1MB (1,000,000 bytes).");
          if (!validSelection(collectionConsent, "sandbox")) throw new Error("Choose an active sandbox agreement.");
          await run("statement", async () => ({ consent_id: collectionConsent, csv: validateStatement(await file.text(), categories) }));
        })} className="bi-form">
          <p className="bi-notice">Unverified bank statement upload · development only. BANK-DERIVED does not mean authenticated or verified. Upload fictional data only.</p>
          <label>Statement CSV<input className="filter-search-input" type="file" accept=".csv,text/csv" required onChange={e => setFile(e.target.files?.[0] || null)} /></label>
          <p>Exact header: <code>date,direction,amount,category,description,balance</code>. 1–2000 rows, at most 1MB. Dates: YYYY-MM-DD (2000 through today); direction: in/out; positive amounts with ≤2 decimals; supported category or blank; description ≤240 characters; balance signed decimal or blank.</p>
          <Button type="submit" disabled={busy || !file || !validSelection(collectionConsent, "sandbox")}>Validate & upload unverified CSV</Button>
        </form>}
      </fieldset>
    </SignalCard>}
    {scope === "cashflow" && <SignalCard title="Manual income / expense" source="DECLARED BY BORROWER" sandbox={sandbox} description="Unverified lender-entered borrower declaration. Kept separate from sandbox and bank-derived records; not used by the current model.">
      <form onSubmit={e => submit(e, async () => {
        if (!validSelection(declaredConsent, "attested")) throw new Error("Choose an active lender attestation.");
        if (!record.category) throw new Error("Category is required.");
        const validated = validateRecord(record, categories);
        if (await run("records", { consent_id: declaredConsent, records: [validated] })) setRecord(r => ({ ...r, amount: "", description: "" }));
      })}>
        <fieldset className="bi-form" disabled={busy}>
          <ConsentSelect title="Recorded borrower authorization · lender attestation" consents={declaredConsents} value={declaredConsent} onChange={setDeclaredConsent} />
          <div className="bi-fields">
            <label>Date<input className="filter-search-input" type="date" min="2000-01-01" max={todayUTC()} required value={record.date} onChange={update("date")} /></label>
            <label>Direction<select className="filter-select" value={record.direction} onChange={update("direction")}><option value="in">Income / inflow</option><option value="out">Expense / outflow</option></select></label>
            <label>Amount (₹)<input className="filter-search-input" type="number" min="0.01" max="1000000000000" step="0.01" required value={record.amount} onChange={update("amount")} /></label>
            <label>Category<select className="filter-select" required value={record.category} onChange={update("category")}><option value="">Choose category</option>{categories.map(c => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}</select></label>
          </div>
          <label>Description (optional; not retained in calculated records)<input className="filter-search-input" maxLength={240} value={record.description} onChange={update("description")} /></label>
          <Button type="submit" disabled={busy || !validSelection(declaredConsent, "attested") || !categories.length}>Save declared record</Button>
        </fieldset>
      </form>
    </SignalCard>}
  </div>;
}
