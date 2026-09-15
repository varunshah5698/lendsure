import { useState, useEffect } from "react";
import { api } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import { SkeletonCard } from "../components/ui/Skeleton";
import "./Security.css";

function State({ value, good = true }) {
  if (value === true || value === "enabled" || value === "active" || value === "restricted") {
    return <span className="sec-ok">● ON</span>;
  }
  if (value === false || value === "not_configured" || value === "unknown" || value == null) {
    return <span className="sec-unknown" title="Not implemented or unknown — never faked">? {String(value ?? "unknown").replace(/_/g, " ").toUpperCase()}</span>;
  }
  return <span className={good ? "sec-ok" : "sec-info"}>{String(value)}</span>;
}

export default function Security() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api("/security/status").then(setData).catch(() => setData({ error: true }));
  }, []);

  if (!data) return <div><PageHeader title="Security Center" /><SkeletonCard /></div>;
  if (data.error) {
    return (
      <div>
        <PageHeader title="Security Center" description="Live control state" />
        <Card><CardContent><p style={{ color: "var(--danger)" }}>Could not reach the security endpoint.</p></CardContent></Card>
      </div>
    );
  }

  const groups = [
    { title: "Authentication", desc: "How users prove identity", items: [
      ["OTP login", data.authentication?.otp], ["Guest sessions", data.authentication?.guest],
      ["Demo OTP mode", data.authentication?.demo_otp_mode ? "ON (demo)" : false],
      ["Passwords", data.authentication?.passwords], ["MFA", data.authentication?.mfa],
    ]},
    { title: "Authorization", desc: "Centralized RBAC — enforced server-side", items: [
      ["RBAC layer", data.rbac?.enabled], ["Roles", (data.rbac?.roles || []).join(", ")],
    ]},
    { title: "API Protection", desc: "Rate limits, CORS, headers, body limits", items: [
      ["Rate limiting", data.rate_limiting?.enabled],
      [`Auth ${data.rate_limiting?.auth_per_min_per_ip}/min · mutations ${data.rate_limiting?.mutations_per_min_per_ip}/min`, true],
      ["CORS", data.cors?.mode], ["CSP headers", data.headers?.csp],
      ["Clickjacking guard", data.headers?.frame_deny], ["Body limit", `${data.body_limit_bytes} bytes`],
    ]},
    { title: "Data & Audit", desc: "What protects records and history", items: [
      ["Database", data.database?.ok], [`Audit events: ${data.audit?.events}`, true],
      ["Append-only audit", data.audit?.append_only], ["Audit hash-chaining", data.audit?.hash_chaining],
      ["Encryption at rest", data.database?.encryption_at_rest], ["Backups", data.backups?.status],
      ["Document malware scan", data.document_malware_scan?.status],
    ]},
    { title: "ML Integrity", desc: "Model provenance", items: [
      ["Model loaded", data.ml?.loaded], ["Model", data.ml?.model_id],
    ]},
  ];

  return (
    <div>
      <PageHeader title="Security Center" description="Real control state — ? means not implemented, never faked" />
      {groups.map((g) => (
        <Card key={g.title} style={{ marginBottom: 16 }}>
          <CardHeader><CardTitle>{g.title}</CardTitle><CardDescription>{g.desc}</CardDescription></CardHeader>
          <CardContent>
            {g.items.map(([label, v]) => (
              <div key={label} className="sec-row">
                <span className="sec-label">{label}</span>
                <State value={v} />
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
      <p className="sec-note">{data.rbac?.note}</p>
    </div>
  );
}
