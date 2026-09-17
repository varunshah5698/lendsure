import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { mlCredit } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonCard } from "../components/ui/Skeleton";

/** The single authoritative scoring explainer: rules engine + live ML model.
 *  Every number below comes from /ml/credit/model (the trained artifact). */
export default function AdminModel() {
  const { session } = useAuth();
  const [model, setModel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    mlCredit.model(session.token).then(setModel).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div><PageHeader title="How Scoring Works" /><SkeletonCard /></div>;
  if (error) return <ErrorState message={error} />;
  if (!model) return null;
  const tm = model.test_real_metrics || {};

  return (
    <div>
      <PageHeader eyebrow="Governance" title="How Scoring Works" description="One place for how LendSure scores borrowers — rules plus the trained model" />

      <Card style={{ marginBottom: 16 }}>
        <CardHeader><CardTitle>1 · Rules engine (deterministic)</CardTitle>
          <CardDescription>Trust across five dimensions, nine fraud checks, affordability math. Same input always gives the same output; every factor is stored with the analysis.</CardDescription></CardHeader>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <CardHeader>
          <CardTitle>2 · ML default model · {model.model_id}</CardTitle>
          <CardDescription>
            Trained on {model.data_source?.real_rows?.toLocaleString()} real borrowers
            ({model.data_source?.real}) plus {(model.data_source?.synthetic_rows || 0).toLocaleString()} synthetic rows.
            Selected by {model.selection_criterion}. Calibrated ({model.calibration}).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
            <Badge variant="APPROVE">Precision {(tm.precision * 100).toFixed(0)}%</Badge>
            <Badge variant="APPROVE">Recall {(tm.recall * 100).toFixed(0)}%</Badge>
            <Badge variant="MANUAL_REVIEW">F2 {tm.f2?.toFixed(2)}</Badge>
            <Badge variant="MANUAL_REVIEW">PR-AUC {tm.pr_auc?.toFixed(2)}</Badge>
            <Badge variant="MEDIUM">ROC-AUC {tm.roc_auc?.toFixed(2)} (reference only)</Badge>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 640 }}>
            Demo model; tuned to catch potential defaults, so some flags will be incorrect.
            About one in two flags is right — built for recall, not for blind trust.
            Measured on {tm.n?.toLocaleString()} real borrowers the model never trained on
            (confusion: {tm.tp} caught, {tm.fn} missed, {tm.fp} false alarms).
          </p>
          {model.test_real_bands?.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data-table">
                <thead><tr><th>Band</th><th>Borrowers</th><th>Observed default rate</th><th>Defaults captured</th></tr></thead>
                <tbody>
                  {model.test_real_bands.map((b) => (
                    <tr key={b.band}>
                      <td><b>{b.band}</b></td>
                      <td>{b.n.toLocaleString()} ({(b.share * 100).toFixed(1)}%)</td>
                      <td>{(b.default_rate * 100).toFixed(1)}%</td>
                      <td>{(b.captured_defaults * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
            Demo model. Age and city are excluded from this version for fairness
            {(model.excluded_features || []).length ? ` (retrained without: ${model.excluded_features.join(", ")})` : ""};
            fairness-relevant features must be reviewed/removed before real-world lending decisions.
            Full provenance (data hashes, splits, candidates) ships in the model artifact metadata.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
