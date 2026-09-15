import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAuth, guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { sim } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";
import { SkeletonCard } from "../components/ui/Skeleton";
import Icon from "../components/ui/Icon";

export default function Simulations() {
  const { session } = useAuth();
  const toast = useToast();
  const [scenarios, setScenarios] = useState([]);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(null);
  const [results, setResults] = useState({});
  const guest = isGuest(session);

  const load = useCallback(async () => {
    try {
      setScenarios(await sim.scenarios(session.token));
    } catch (e) { setError(e.message); }
  }, [session?.token]);

  useEffect(() => { load(); }, [load]);

  const run = async (id) => {
    if (!guardLender(session, toast)) return;
    try {
      setRunning(id);
      const r = await sim.run(id, session.token);
      setResults((p) => ({ ...p, [id]: r }));
      toast.success("Scenario completed — all records flagged SIMULATION");
    } catch (e) { toast.error("Scenario failed: " + e.message); }
    finally { setRunning(null); }
  };

  const cleanup = async () => {
    if (!guardLender(session, toast)) return;
    if (!window.confirm("Delete ALL simulation (SIM-*) records?")) return;
    try {
      const r = await sim.cleanup(session.token);
      const n = Object.values(r.deleted || {}).reduce((a, b) => a + b, 0);
      toast.success(`Simulation data wiped (${n} rows)`);
      setResults({});
    } catch (e) { toast.error("Cleanup failed: " + e.message); }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div>
      <PageHeader
        title="Simulation Center"
        description="Scripted scenarios executing real backend services on SIM-flagged records — isolated from production metrics"
        actions={<Button variant="ghost" size="sm" disabled={guest} onClick={cleanup}>Cleanup SIM data</Button>}
      />
      <div className="bd-grid">
        {scenarios.map((s) => (
          <Card key={s.id}>
            <CardHeader><CardTitle>{s.title}</CardTitle><CardDescription>{s.desc}</CardDescription></CardHeader>
            <CardContent>
              <Button variant="primary" size="sm" disabled={running === s.id || guest}
                title={guest ? "Sign in with Phone OTP" : "Run scenario"}
                onClick={() => run(s.id)}>
                {running === s.id ? "Running…" : "Run scenario"}
              </Button>
              {results[s.id] && (
                <div style={{ marginTop: 12 }}>
                  {results[s.id].steps.map((st, i) => (
                    <div key={i} className="audit-row">
                      <div>{st.ok ? "✓" : <Icon name="x" size={12} style={{ display: "inline", verticalAlign: "-1px" }} />} <b>{st.step}</b><br />
                        <small style={{ color: "var(--text-muted)" }}>{st.detail}</small></div>
                      {st.link && <Link to={st.link} className="link-btn" style={{ fontSize: 12 }}>open →</Link>}
                    </div>
                  ))}
                  <p style={{ fontSize: 11, color: "var(--text-muted)" }}>{results[s.id].note}</p>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      {!scenarios.length && !error && <EmptyState title="Loading scenarios…" />}
    </div>
  );
}
