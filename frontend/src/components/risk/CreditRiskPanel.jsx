import { useState, useEffect } from "react";
import { mlCredit } from "../../lib/api";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../ui/Card";
import Badge from "../ui/Badge";
import Icon from "../ui/Icon";
import { SkeletonCard } from "../ui/Skeleton";

const BAND_COLOR = { Low: "var(--success)", Medium: "#b7791f", High: "var(--warning)", Critical: "var(--danger)" };

/** Live output of the trained credit-v4 default model — no placeholders.
 *  Renders nothing at all if the model artifacts are not installed. */
export default function CreditRiskPanel({ borrowerId, token }) {
  const [data, setData] = useState(null);
  const [stats, setStats] = useState(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let live = true;
    mlCredit.predict(borrowerId, token)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live && /503|not installed/i.test(e.message)) setMissing(true); });
    mlCredit.model(token)
      .then((m) => { if (live) setStats(m.test_real_metrics || null); })
      .catch(() => {});
    return () => { live = false; };
  }, [borrowerId, token]);

  if (missing || !data) return null;

  const pct = Math.round(data.default_probability * 1000) / 10;
  return (
    <Card style={{ marginBottom: 16 }}>
      <CardHeader>
        <CardTitle>Default prediction · {data.model_id}</CardTitle>
        <CardDescription>Trained gradient-boosting model on real + synthetic borrowers — scored live just now</CardDescription>
      </CardHeader>
      <CardContent>
        <div style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
          <div style={{ textAlign: "center", minWidth: 110 }}>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 40, fontWeight: 700, lineHeight: 1 }}>{data.risk_score}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 700, letterSpacing: ".06em" }}>RISK SCORE / 100</div>
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <Badge variant={data.risk_category === "Low" ? "APPROVE" : data.risk_category === "Critical" ? "REJECT" : "MANUAL_REVIEW"}>
                {data.risk_category.toUpperCase()} RISK
              </Badge>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{pct}% default probability</span>
            </div>
            <div style={{ height: 8, borderRadius: 4, background: "var(--bg-alt)", overflow: "hidden" }}>
              <div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", borderRadius: 4, background: BAND_COLOR[data.risk_category] || "var(--primary)" }} />
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
              Recovery priority <b>{data.recovery_priority.code}</b> — {data.recovery_priority.action}. <i>{data.recovery_priority.why}.</i>
            </div>
          </div>
        </div>
        {data.factors?.length > 0 && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".07em", color: "var(--text-muted)", marginBottom: 8 }}>TOP DRIVERS FOR THIS BORROWER</div>
            {data.factors.map((f) => (
              <div key={f.feature} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "5px 0", borderBottom: "1px solid var(--border-light)" }}>
                <Icon name={f.direction === "increases risk" ? "flag" : "check-circle"} size={14} />
                <b>{f.label}</b>
                <span style={{ color: "var(--text-muted)" }}>· {f.direction}</span>
              </div>
            ))}
          </div>
        )}
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
          Demo model; tuned to catch potential defaults, so some flags will be incorrect.
          {stats ? ` Measured precision ${(stats.precision * 100).toFixed(0)}% · recall ${(stats.recall * 100).toFixed(0)}% · PR-AUC ${stats.pr_auc?.toFixed(2)} on ${stats.n?.toLocaleString()} real borrowers.` : ""}
        </p>
      </CardContent>
    </Card>
  );
}

export function CreditRiskSkeleton() {
  return <SkeletonCard />;
}
