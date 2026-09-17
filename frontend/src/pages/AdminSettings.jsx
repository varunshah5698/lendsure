import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { admin } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import CopyButton from "../components/ui/CopyButton";
import EmptyState from "../components/ui/EmptyState";
import ErrorState from "../components/ui/ErrorState";
import { formatDate } from "../lib/dates";
import { SkeletonTable } from "../components/ui/Skeleton";

export default function AdminSettings() {
  const { session } = useAuth();
  const toast = useToast();
  const [keys, setKeys] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyScope, setNewKeyScope] = useState("read");
  const [newKeyDays, setNewKeyDays] = useState(90);
  const [newKey, setNewKey] = useState(null);
  const [newKeyMeta, setNewKeyMeta] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      setLoading(true);
      const [k, s] = await Promise.all([admin.keys(session.token), admin.sessions(session.token)]);
      setKeys(k);
      setSessions(s);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [session?.token]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const createKey = async () => {
    if (!guardLender(session, toast)) return;
    if (newKeyName.trim().length < 2) return toast.error("Give the key a label");
    try {
      const d = await admin.createKey(newKeyName.trim(), session.token, { scopes: newKeyScope, expires_days: newKeyDays });
      setNewKey(d.key);
      setNewKeyMeta({ scopes: d.scopes, expires_at: d.expires_at });
      setNewKeyName("");
      toast.success("API key created");
      loadAll();
    } catch (e) { toast.error("Creation failed: " + e.message); }
  };

  const revokeKey = async (id) => {
    if (!guardLender(session, toast)) return;
    try {
      await admin.revokeKey(id, session.token);
      toast.success("Key revoked");
      loadAll();
    } catch (e) { toast.error("Revocation failed: " + e.message); }
  };

  const revokeSession = async (tok, label) => {
    if (!guardLender(session, toast)) return;
    if (!window.confirm(`Sign out "${label}"?`)) return;
    try {
      await admin.revokeSession(tok, session.token);
      toast.success("Session revoked");
      loadAll();
    } catch (e) { toast.error("Revocation failed: " + e.message); }
  };

  const signOutOthers = async () => {
    if (!guardLender(session, toast)) return;
    const others = sessions.filter((s) => !s.expired && !s.current);
    if (!others.length) return;
    if (!window.confirm(`Sign out ${others.length} other session(s)?`)) return;
    try {
      for (const s of others) await admin.revokeSession(s.token, session.token);
      toast.success(`${others.length} session(s) revoked`);
      loadAll();
    } catch (e) { toast.error("Failed: " + e.message); }
  };

  if (loading) return <div><PageHeader title="Settings" /><SkeletonTable rows={4} cols={5} /></div>;
  if (error) return <ErrorState message={error} />;

  return (
    <div>
      <PageHeader
        eyebrow="Governance"
        title="Settings"
        description="API keys and system configuration"
        actions={sessions.some((s) => !s.expired && !s.current) ? (
          <Button variant="secondary" size="sm" onClick={signOutOthers}>Sign out other devices</Button>
        ) : null}
      />

      <Card>
        <CardHeader>
          <CardTitle>API Keys</CardTitle>
          <CardDescription>Per-lender keys for programmatic access. Send as <code>X-API-Key</code> header. Full key is shown once.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="settings-key-create">
            <input
              type="text"
              placeholder="Key label, e.g. field-tablet-3"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              className="filter-search-input"
              style={{ maxWidth: 300 }}
            />
            <select value={newKeyScope} onChange={(e) => setNewKeyScope(e.target.value)} className="filter-select" title="Permission scope">
              <option value="read">read-only</option>
              <option value="write">read + write</option>
              <option value="admin">admin (full)</option>
            </select>
            <select value={newKeyDays} onChange={(e) => setNewKeyDays(Number(e.target.value))} className="filter-select" title="Expiry">
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
              <option value={365}>1 year</option>
            </select>
            <Button variant="primary" size="sm" onClick={createKey} disabled={isGuest(session)} title={isGuest(session) ? "Sign in with Phone OTP for lender actions" : "Create API key"}>＋ Create key</Button>
          </div>

          {newKey && (
            <div className="settings-key-once">
              <span>New key — copy now, it won't be shown again{newKeyMeta ? ` (${newKeyMeta.scopes}, expires ${formatDate(newKeyMeta.expires_at)})` : ""}:</span>
              <code className="settings-key-value">{newKey}</code>
              <CopyButton text={newKey} label="Key" />
            </div>
          )}

          {keys.length ? (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data-table">
                <thead>
                  <tr><th>Label</th><th>Key</th><th>Scopes</th><th>Expires</th><th>Created</th><th>Last used</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k.id}>
                      <td><b>{k.name}</b></td>
                      <td><code style={{ fontSize: 12 }}>{k.prefix}</code></td>
                      <td style={{ fontSize: 12 }}>{k.scopes || "read"}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{k.expires_at ? formatDate(k.expires_at, { dateOnly: true }) : "never (legacy)"}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{formatDate(k.created_at, { dateOnly: true })}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{k.last_used ? formatDate(k.last_used) : "—"}</td>
                      <td>{k.revoked || k.expired ? <Badge variant="HIGH">{k.expired && !k.revoked ? "Expired" : "Revoked"}</Badge> : <Badge variant="APPROVE">Active</Badge>}</td>
                      <td>{!k.revoked && <Button variant="ghost" size="sm" onClick={() => revokeKey(k.id)} disabled={isGuest(session)} title={isGuest(session) ? "Sign in with Phone OTP for lender actions" : "Revoke key"}>Revoke</Button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No keys yet" icon="lock" description="Create an API key to access LendSure programmatically." />
          )}
        </CardContent>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <CardHeader>
          <CardTitle>Active Sessions</CardTitle>
          <CardDescription>Signed-in lenders and guests. Revoking a session signs that device out immediately.</CardDescription>
        </CardHeader>
        <CardContent>
          {sessions.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>User</th><th>Role</th><th>Phone</th><th>Signed in</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={s.id}>
                      <td><b>{s.display_name}</b> <code style={{ fontSize: 11 }}>{s.token_prefix}</code>{s.current ? <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700 }}> · this device</span> : ""}</td>
                      <td style={{ textTransform: "capitalize" }}>{s.role}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{s.phone}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{formatDate(s.created_at)}</td>
                      <td>{s.expired ? <Badge variant="HIGH">Expired</Badge> : <Badge variant="APPROVE">Active</Badge>}</td>
                      <td>
                        {!s.expired && (
                          <Button variant="ghost" size="sm" onClick={() => revokeSession(s.id, s.display_name)} disabled={isGuest(session)} title={isGuest(session) ? "Sign in with Phone OTP for lender actions" : "Sign out session"}>
                            Sign out
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No sessions" icon="user" description="No active sign-ins found." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
