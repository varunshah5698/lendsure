import CashFlowChart from "../charts/CashFlowChart";
import { SignalCard, Metrics, DataTable, label, money, signedMoney } from "./IntelligenceShared";

const moneyKeys = new Set(["monthly_inflow", "monthly_outflow", "net_cash_flow", "average_monthly_balance", "minimum_balance"]);

export default function CashflowSignals({ summaries, sandbox }) {
  if (!summaries?.length) return <SignalCard title="Cashflow signals" sandbox={sandbox} description="No accessible records. Missing data is not zero income or zero expenses."><p>Declared records require recorded borrower authorization and lender attestation. Account Aggregator (AA) is unavailable / not connected.</p></SignalCard>;
  return <div className="bi-stack">{summaries.map(summary => {
    const months = summary.months || [];
    const provenance = { source: summary.source, sandbox };
    const points = months.map(m => ({ label: m.month, values: m }));
    return <section className="bi-stack" key={summary.source} aria-label={`${summary.source} cashflow`}>
      <SignalCard title="Cashflow · calculated metrics" {...provenance} description={summary.confidence}>
        <p>Fetched: {summary.fetched_at} · Records: {summary.record_count}</p>
        <p>Coverage: {months.length} observed months{months.length ? ` · ${months[0].month} to ${months[months.length - 1].month}` : ""}. Missing months: {summary.missing_months?.length ? summary.missing_months.join(", ") : "None within the observed window"}. Coverage does not establish completeness.</p>
        {summary.source === "BANK-DERIVED" && <p className="bi-notice">Development statement upload — unverified bank statement, not an authenticated bank feed.</p>}
        <Metrics rows={Object.entries(summary.metrics || {}).filter(([key]) => key !== "recurring_obligations").map(([key, value]) => [label(key), value == null ? "Unavailable — insufficient observations" : key.endsWith("_pct") ? `${value}%` : key === "net_cash_flow" ? signedMoney(value) : moneyKeys.has(key) ? money(value) : value])} />
      </SignalCard>
      <SignalCard title="Monthly flows" {...provenance} description="Observed months only; missing months are not zero-filled. Inflow is not the same as income.">
        <CashFlowChart title="Inflow / outflow" points={points} series={[{ key: "inflow", label: "Inflow", color: "var(--success)" }, { key: "outflow", label: "Outflow", color: "var(--warning)" }]} format={money} />
        <CashFlowChart title="Signed net trend" points={points} series={[{ key: "net", label: "Net cash flow", color: "var(--primary)" }]} format={signedMoney} />
        {months.some(m => m.balance != null) ? <CashFlowChart title="Observed balance trend" subtitle="Unknown balances remain gaps, not zero. Not a daily average." points={points} series={[{ key: "balance", label: "Balance", color: "var(--info)" }]} format={signedMoney} /> : <p>Balance trend unavailable — no supported balances.</p>}
        <DataTable caption="Monthly observations" rows={months} columns={[["month", "Month"], ["inflow", "Inflow", money], ["outflow", "Outflow", money], ["net", "Net", signedMoney], ["balance", "Balance", money]]} />
      </SignalCard>
      <SignalCard title="Categories & recurring outgoings" {...provenance}>
        {!!summary.expense_categories?.length && <CashFlowChart title="Expense categories" points={summary.expense_categories.map(c => ({ label: c.category, values: { amount: c.amount } }))} series={[{ key: "amount", label: "Observed expenses", color: "var(--warning)" }]} format={money} />}
        <DataTable caption="Expense categories" rows={summary.expense_categories} empty="No outgoing categories observed." columns={[["category", "Category"], ["amount", "Amount", money]]} />
        <DataTable caption="Recurring outgoing categories (not contractual obligations)" rows={summary.metrics?.recurring_obligations} empty="No categories recur across two observed months." columns={[["category", "Category"], ["amount", "Per observed month", money], ["months_observed", "Months observed"]]} />
        <p>Income category totals are not supplied by this API; only the largest income category is available above.</p>
      </SignalCard>
      <SignalCard title="Calculation provenance" {...provenance}>
        <dl className="bi-semantics">{Object.entries(summary.semantics || {}).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{Array.isArray(value) ? value.join(", ") || "None" : value}</dd></div>)}</dl>
      </SignalCard>
    </section>;
  })}</div>;
}
