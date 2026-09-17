import { useCallback, useEffect, useRef, useState } from "react";
import { intelligence } from "../../lib/api";
import Button from "../ui/Button";
import TraditionalCredit from "./TraditionalCredit";
import CashflowSignals from "./CashflowSignals";
import IntelligenceControls from "./IntelligenceControls";
import { SignalCard, Metrics, money, signedMoney } from "./IntelligenceShared";
import "./BorrowerIntelligence.css";

export function ModelNotice() {
  return <p className="bi-model-notice">Retraining required: new credit and cashflow signals are not used by the current model. Existing scores and recommendations do not incorporate these signals. Deterministic calculations only; no LLM assessment.</p>;
}

function unavailableCard(title) {
  return <SignalCard title={title} description="Private borrower intelligence is available only to lenders with an explicit access grant. No private API request is made for guests."><p>Sign in as a lender and contact an authorized operator to provision access. There is no self-grant action.</p></SignalCard>;
}

export default function BorrowerIntelligence({ bid, session, view }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState("");
  const [clock, setClock] = useState(Date.now());
  const controller = useRef(null);
  const locked = useRef(false);
  const allowed = session?.role === "lender";
  const request = useCallback(async (method = "get", payload) => {
    const current = controller.current;
    if (!allowed || !current || current.signal.aborted || locked.current) return false;
    locked.current = true;
    setBusy(true); setError(null); setMessage("");
    try {
      const body = typeof payload === "function" ? await payload() : payload;
      if (current.signal.aborted) return false;
      const result = method === "get" ? await intelligence.get(bid, current.signal) : await intelligence[method](bid, body, current.signal);
      if (current.signal.aborted) return false;
      if (method !== "get") {
        setMessage(result?.added != null ? `${result.added} records added; ${result.duplicates} duplicates skipped.` : method === "revoke" ? "Revoked. Signals under that authorization are no longer accessible." : "Saved. Intelligence refreshed.");
      }
      const next = await intelligence.get(bid, current.signal);
      if (current.signal.aborted) return false;
      setData(next); setClock(Date.now());
      return true;
    } catch (e) {
      if (!current.signal.aborted) { setError(e); setData(null); }
      return false;
    } finally {
      if (!current.signal.aborted) { locked.current = false; setBusy(false); }
    }
  }, [bid, allowed]);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    locked.current = false;
    setData(null); setError(null); setMessage(""); setBusy(false);
    if (allowed) request();
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => { current.abort(); clearInterval(timer); };
  }, [request, session, view]);

  const sandbox = bid.startsWith("DEMO-") && data?.access?.demo_only === true;
  const expired = data?.consents?.some(c => ["sandbox", "attested"].includes(c.status) && new Date(c.expires_at).getTime() <= clock);
  const denied = error?.status === 403;
  return <section className="bi" aria-label="Borrower financial intelligence" aria-busy={busy}>
    <ModelNotice />
    {!allowed ? unavailableCard() : <>
      <div className="bi-actions"><h2>{view === "overview" ? "Unified financial overview" : view === "credit" ? "Traditional credit intelligence" : "Financial intelligence"}</h2><Button variant="secondary" size="sm" disabled={busy} onClick={() => request()}>{busy ? "Loading…" : "Refresh intelligence"}</Button></div>
      {busy && <p role="status">Loading private intelligence…</p>}
      {message && <p role="status">{message}</p>}
      {error && <SignalCard title={denied ? "Private access denied (403)" : "Intelligence unavailable"}>
        <p role="alert">{denied ? "Access denied. Contact an authorized operator to provision or review your explicit borrower access grant or authorization. This screen cannot grant access." : error.message}</p>
        <Button variant="secondary" disabled={busy} onClick={() => request()}>Retry access / reload</Button>
        <p>A failed collection is not automatically retried. Reload to check whether it completed before submitting again.</p>
      </SignalCard>}
      {expired && <SignalCard title="Authorization expired" sandbox={sandbox}><p>Signals are hidden until access is refreshed. Record a new agreement or attestation only if appropriate.</p><Button disabled={busy} onClick={() => request()}>Refresh authorization status</Button></SignalCard>}
      {data && !expired && <>
        <SignalCard title="Provider availability & provenance" sandbox={sandbox}>
          <Metrics rows={[["TransUnion CIBIL", "Unavailable / not connected"], ["Account Aggregator (AA)", "Unavailable / not connected"], ["Configured credit provider", `${data.providers?.credit?.provider || "Unavailable"} · ${data.providers?.credit?.status || "unavailable"}`], ["Configured bank provider", `${data.providers?.bank?.provider || "Unavailable"} · ${data.providers?.bank?.status || "unavailable"}`]]} />
          <p>Traditional credit, each cashflow source, and internal repayment records remain separate. No composite score, inferred income, or live bank connection is fabricated.</p>
        </SignalCard>
        {view === "overview" ? <FinancialOverview data={data} sandbox={sandbox} /> : <>
          <IntelligenceControls key={`${bid}:${view}`} data={data} bid={bid} scope={view === "credit" ? "credit" : "cashflow"} busy={busy} run={request} />
          {view === "credit" ? <TraditionalCredit report={data.credit} sandbox={sandbox} /> : <CashflowSignals summaries={data.cashflow} sandbox={sandbox} />}
        </>}
      </>}
    </>}
  </section>;
}

function FinancialOverview({ data, sandbox }) {
  const credit = data.credit;
  const internal = data.internal || {};
  return <div className="bi-overview">
    <SignalCard title="Traditional credit" source={credit?.source} sandbox={sandbox} description={credit ? `${credit.provider} · fetched ${credit.fetched_at}` : "No accessible report. Not an internal model score."}>
      <Metrics rows={[["Reported score", credit?.score], ["Score range", credit?.score_min == null ? null : `${credit.score_min}–${credit.score_max}`], ["Utilization", credit?.utilization_pct == null ? null : `${credit.utilization_pct}%`], ["Report date", credit?.report_date], ["Freshness", credit ? credit.stale ? "Stale / date unknown" : "Within 30 days" : null]]} />
    </SignalCard>
    {data.cashflow?.length ? data.cashflow.map(s => <SignalCard key={s.source} title="Cashflow summary" source={s.source} sandbox={sandbox} description={s.confidence}>
      <Metrics rows={[["Average monthly inflow", money(s.metrics?.monthly_inflow)], ["Average monthly outflow", money(s.metrics?.monthly_outflow)], ["Average signed net", signedMoney(s.metrics?.net_cash_flow)], ["Observed months", s.months?.length], ["Records", s.record_count], ["Fetched", s.fetched_at]]} />
      <p>Missing months: {s.missing_months?.length ? s.missing_months.join(", ") : "None within observed window"}. Missing months excluded, not zero-filled.</p>
    </SignalCard>) : <SignalCard title="Cashflow summary" sandbox={sandbox} description="Unavailable — no accessible cashflow records. No income or expense statistics inferred." />}
    <SignalCard title="Internal repayment summary" source="INTERNAL REPAYMENT RECORDS" sandbox={sandbox} description="Internal servicing history only; not bureau payment history or bank-derived cashflow.">
      <Metrics rows={[["Loans completed", internal.loans_completed], ["On-time repayments", internal.repayments_on_time], ["Missed repayments", internal.repayments_missed], ["Amount repaid", money(internal.amount_repaid)], ["Updated", internal.updated_at]]} />
      {!Object.keys(internal).length && <p>No accessible internal repayment records supplied.</p>}
    </SignalCard>
  </div>;
}
