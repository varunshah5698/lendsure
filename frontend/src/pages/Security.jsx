import { useState, useEffect } from "react";
import { api, auth } from "../lib/api";
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
  const [sessions, setSessions] = useState(null);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    api("/security/status").then(setData).catch(() => setData({ error: true }));
    auth.sessions().then(setSessions).catch(() => setSessions({ sessions: [] }));
  }, []);

  const revokeAll = async () => {
    if (!window.confirm("Sign out all other devices? This device stays signed in.")) return;
    setRevoking(true);
    try {
      const r = await auth.revokeAllSessions();
      setSessions(await auth.sessions());
      alert(`Signed out ${r.revoked} other session${r.revoked === 1 ? "" : "s"}.`);
    } catch (e) {
      alert(e.message);
    }
    setRevoking(false);
  };

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

  const sessList = sessions?.sessions || [];

  return (
    <div>
      <PageHeader title="Security Center" description="Real control state — ? means not implemented, never faked" />
      <Card style={{ marginBottom: 16 }}>
        <CardHeader><CardTitle>My sessions ({sessList.length})</CardTitle>
          <CardDescription>Every device signed in as you — stay here, kill the rest</CardDescription></CardHeader>
        <CardContent>
          {sessList.length === 0 && <p className="sec-note">No sessions found.</p>}
          {sessList.map((s, i) => (
            <div key={i} className="sec-row">
              <span className="sec-label">
                {s.display_name} · {s.ip || "unknown IP"}{" "}
                <span className="sec-info">· {s.remembered ? "remembered" : "standard"} · last active {s.last_active ? String(s.last_active).slice(0, 16).replace("T", " ") : "—"}</span>
              </span>
              {s.current
                ? <span className="sec-ok">● THIS DEVICE</span>
                : <span className="sec-info">other device</span>}
            </div>
          ))}
          <button className="sec-danger-btn" onClick={revokeAll} disabled={revoking}>
            {revoking ? "Signing out…" : "Sign out all other devices"}
          </button>
        </CardContent>
      </Card>
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
