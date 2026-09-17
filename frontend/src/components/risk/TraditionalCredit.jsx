import CashFlowChart from "../charts/CashFlowChart";
import Badge from "../ui/Badge";
import { SignalCard, Metrics, DataTable, money, valueText } from "./IntelligenceShared";

export default function TraditionalCredit({ report, sandbox }) {
  if (!report) return <SignalCard title="Traditional credit" sandbox={sandbox} description="No accessible report. TransUnion CIBIL is unavailable / not connected; no live bureau score is inferred."><p>Use an existing sandbox agreement to fetch a fictional report only when the server enables it.</p></SignalCard>;
  const provenance = { source: report.source, sandbox };
  const pct = (v) => v == null ? "Unavailable" : `${v}%`;
  return <div className="bi-stack">
    <SignalCard title="Traditional credit report" {...provenance} description={`${report.provider} · fetched ${report.fetched_at}`}>
      <Badge variant={report.stale ? "warning" : "info"}>{report.stale ? "Stale / report date unknown" : "Report within 30 days"}</Badge>
      <Metrics rows={[
        ["Report date", report.report_date], ["Reference", report.reference_id],
        ["Score", report.score], ["Score range", report.score_min == null ? null : `${report.score_min}–${report.score_max}`],
        ["History (months)", report.history_months], ["Active accounts", report.active_accounts], ["Closed accounts", report.closed_accounts],
        ["Secured loans", report.secured_loans], ["Unsecured loans", report.unsecured_loans],
        ["Utilization", pct(report.utilization_pct)], ["On-time payments", pct(report.on_time_payment_pct)], ["Overdue amount", money(report.overdue_amount)],
      ]} />
      <p>Default indicators: {report.default_indicators == null ? "Unavailable" : report.default_indicators.length ? report.default_indicators.join(" · ") : "None reported"}</p>
    </SignalCard>
    <SignalCard title="Utilization & recent changes" {...provenance}>
      {report.utilization_trend?.length ? <CashFlowChart title="Reported utilization" points={report.utilization_trend.map(p => ({ label: p.date, values: { utilization: p.value } }))} series={[{ key: "utilization", label: "Utilization", color: "var(--info)" }]} format={pct} /> : <p>Utilization trend unavailable — not supplied.</p>}
      <DataTable caption="Utilization observations" rows={report.utilization_trend} columns={[["date", "Date"], ["value", "Utilization", pct]]} />
      <h4>Recent changes</h4>
      {report.recent_changes?.length ? <ul>{report.recent_changes.map((v, i) => <li key={i}>{v}</li>)}</ul> : <p>{report.recent_changes == null ? "Unavailable — not supplied." : "No changes reported."}</p>}
    </SignalCard>
    <SignalCard title="Credit timeline" {...provenance}>
      {report.events?.length ? <ol className="bi-timeline">{[...report.events].sort((a, b) => a.date.localeCompare(b.date)).map((event, i) => <li key={i}><time>{event.date}</time><b>{event.type}</b><span>{valueText(event.description)}</span></li>)}</ol> : <p>{report.events == null ? "Timeline unavailable." : "No events reported."}</p>}
      <DataTable caption="Inquiries" rows={report.inquiries} empty="No inquiries reported." columns={[["date", "Date"], ["purpose", "Purpose"]]} />
    </SignalCard>
    <SignalCard title="Reported accounts" {...provenance}>
      <DataTable caption="Credit accounts" rows={report.accounts} empty="No accounts reported." columns={[
        ["type", "Type"], ["status", "Status"], ["secured", "Secured"], ["balance", "Balance", money], ["credit_limit", "Limit", money], ["overdue_amount", "Overdue", money], ["opened_at", "Opened"], ["closed_at", "Closed"],
      ]} />
    </SignalCard>
  </div>;
}
