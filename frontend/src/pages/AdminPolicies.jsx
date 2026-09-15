import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { admin } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Modal from "../components/ui/Modal";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonCard } from "../components/ui/Skeleton";
import "./AdminPolicies.css";

const POLICY_GROUPS = [
  {
    title: "Risk Thresholds",
    desc: "Bands used to classify borrower risk levels.",
    keys: [
      { key: "risk_low_max", label: "Low Risk Threshold", help: "Applications below this risk score are classified as low risk." },
      { key: "risk_medium_max", label: "Medium Risk Threshold", help: "Applications below this score (but above low) are medium risk." },
    ],
  },
  {
    title: "Fraud Thresholds",
    desc: "Bands for fraud risk classification.",
    keys: [
      { key: "fraud_low_max", label: "Low Fraud Threshold", help: "Below this fraud score = low fraud risk." },
      { key: "fraud_medium_max", label: "Medium Fraud Threshold", help: "Below this fraud score (but above low) = medium fraud risk." },
    ],
  },
  {
    title: "Model Configuration",
    desc: "How the ML model and rules are blended.",
    keys: [
      { key: "ml_blend", label: "ML Blend", help: "0 = pure rules, 1 = pure ML. Default 0.5 = 50/50." },
    ],
  },
  {
    title: "Lending Policy",
    desc: "Constraints on approved loan terms.",
    keys: [
      { key: "max_tenure_months", label: "Max Tenure (months)", help: "Maximum loan duration for any approval." },
      { key: "high_risk_tenure_cap", label: "High Risk Tenure Cap", help: "Maximum tenure for high-risk borrowers." },
      { key: "approve_trust_min", label: "Min Trust for Approval", help: "Minimum trust score to receive an outright approval." },
      { key: "min_recommended_ratio", label: "Min Recommended Ratio", help: "Minimum fraction of requested amount to recommend." },
    ],
  },
  {
    title: "Decision Thresholds",
    desc: "Score boundaries that trigger specific decisions.",
    keys: [
      { key: "manual_review_fraud_score", label: "Manual Review Fraud Score", help: "Fraud scores above this trigger manual review." },
      { key: "reject_risk_score", label: "Reject Risk Score", help: "Risk scores above this trigger rejection." },
    ],
  },
];

export default function AdminPolicies() {
  const { session } = useAuth();
  const toast = useToast();
  const [config, setConfig] = useState(null);
  const [draft, setDraft] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [changes, setChanges] = useState([]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const c = await admin.config(session.token);
      setConfig(c);
      setDraft({});
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange = (key, val) => {
    setDraft((prev) => ({ ...prev, [key]: val }));
  };

  const changedKeys = Object.keys(draft).filter((k) => String(draft[k]) !== String(config?.[k]));

  const handleSave = () => {
    if (!guardLender(session, toast)) return;
    const ch = changedKeys.map((k) => ({ key: k, from: config[k], to: draft[k] }));
    setChanges(ch);
    setShowConfirm(true);
  };

  const confirmSave = async () => {
    try {
      for (const k of changedKeys) {
        const val = String(draft[k]).includes(",") ? draft[k].split(",").map(Number) : Number(draft[k]);
        await admin.updateConfig(k, val, session.token);
      }
      toast.success("Risk policy updated");
      setShowConfirm(false);
      setDraft({});
      load();
    } catch (e) { toast.error("Save failed: " + e.message); }
  };

  if (loading) return <div><PageHeader title="Risk Policies" /><SkeletonCard /><SkeletonCard /></div>;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div>
      <PageHeader
        title="Risk Policies"
        description="Thresholds and bands used by every engine"
        actions={changedKeys.length > 0 ? (
          <div className="policy-actions">
            <Button variant="ghost" size="sm" onClick={() => setDraft({})}>Cancel</Button>
            <Button variant="primary" size="sm" onClick={handleSave} disabled={isGuest(session)} title={isGuest(session) ? "Sign in with Phone OTP for lender actions" : "Save policy changes"}>Save Changes</Button>
          </div>
        ) : null}
      />

      {changedKeys.length > 0 && (
        <div className="policy-unsaved">
          {changedKeys.length} unsaved change{changedKeys.length > 1 ? "s" : ""}
        </div>
      )}

      {POLICY_GROUPS.map((group) => (
        <Card key={group.title} style={{ marginBottom: 16 }}>
          <CardHeader><CardTitle>{group.title}</CardTitle><CardDescription>{group.desc}</CardDescription></CardHeader>
          <CardContent>
            <div className="policy-grid">
              {group.keys.map(({ key, label, help }) => (
                <div key={key} className="policy-field">
                  <label className="policy-label">{label}</label>
                  <input
                    type="number"
                    step="any"
                    value={draft[key] ?? config?.[key] ?? ""}
                    onChange={(e) => handleChange(key, e.target.value)}
                    className={`policy-input ${changedKeys.includes(key) ? "policy-input-changed" : ""}`}
                  />
                  <span className="policy-help">{help}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      <Modal
        open={showConfirm}
        onClose={() => setShowConfirm(false)}
        title="Review Risk Policy Changes"
        description="These changes may affect future lending decisions."
        actions={
          <>
            <Button variant="ghost" onClick={() => setShowConfirm(false)}>Cancel</Button>
            <Button variant="primary" onClick={confirmSave}>Save Changes</Button>
          </>
        }
      >
        <div className="policy-confirm-list">
          {changes.map(({ key, from, to }) => (
            <div key={key} className="policy-confirm-row">
              <span className="policy-confirm-key">{key}</span>
              <span className="policy-confirm-from">{String(from)}</span>
              <span className="policy-confirm-arrow">→</span>
              <span className="policy-confirm-to">{String(to)}</span>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
