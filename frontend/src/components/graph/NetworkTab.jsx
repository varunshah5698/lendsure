import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { graph, cases } from "../../lib/api";
import { useToast } from "../ui/Toast";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../ui/Card";
import Button from "../ui/Button";
import Badge from "../ui/Badge";
import EmptyState from "../ui/EmptyState";
import { SkeletonCard } from "../ui/Skeleton";

/**
 * Graph investigation: real shared-identifier network for one borrower.
 * Connections, path finder and case creation — all backed by stored data.
 */
export default function NetworkTab({ bid, token, guest }) {
  const toast = useToast();
  const [sum, setSum] = useState(null);
  const [hood, setHood] = useState(null);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState("");
  const [path, setPath] = useState(null);
  const [pathBusy, setPathBusy] = useState(false);
  const [inspected, setInspected] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [s, h] = await Promise.all([
        graph.summary(bid, token),
        graph.neighborhood(bid, 2, token),
      ]);
      setSum(s);
      setHood(h);
    } catch (e) { toast.error("Network load failed: " + e.message); }
    finally { setLoading(false); }
  }, [bid, token]);

  useEffect(() => { load(); }, [load]);

  const runPath = async () => {
    if (target.trim().length < 3) return toast.error("Enter a borrower ID, e.g. B10005");
    try {
      setPathBusy(true);
      setPath(await graph.path(bid, target.trim(), token));
    } catch (e) { toast.error("Path search failed: " + e.message); }
    finally { setPathBusy(false); }
  };

  const openCase = async () => {
    if (guest) return toast.error("Guests are read-only — sign in with Phone OTP for lender actions");
    try {
      await cases.create({
        title: `Network review — ${bid}`,
        kind: "network",
        borrower_id: bid,
        evidence: { summary: sum, queried_at: new Date().toISOString() },
      }, token);
      toast.success("Investigation case opened");
    } catch (e) { toast.error("Case creation failed: " + e.message); }
  };

  if (loading) return <><SkeletonCard /><SkeletonCard /></>;
  if (!sum) return <EmptyState title="Network unavailable" />;

  const links = (sum.shared || []).flatMap((s) => s.linked_borrowers.map((b) => ({ ...b, via: s })));
  const hoodEdges = (hood?.edges || []).filter((e) => e.source === `borrower:${bid}` || e.target === `borrower:${bid}`);

  return (
    <div>
      <div className="dash-metrics" style={{ marginBottom: 16 }}>
        <div className="metric-card"><small>Identifiers on file</small><b>{sum.identifiers_on_file}/5</b></div>
        <div className="metric-card"><small>Linked borrowers</small><b>{sum.linked_borrowers}</b></div>
        <div className="metric-card"><small>Neighborhood</small><b>{hood?.nodes?.length || 0} nodes · {hood?.edges?.length || 0} edges</b></div>
        <div className="metric-card"><small>Engine</small><b style={{ fontSize: 13 }}>live query</b></div>
      </div>

      <div className="bd-grid">
        <Card>
          <CardHeader>
            <CardTitle>Connections</CardTitle>
            <CardDescription>Shared identifiers are network exposure — not fraud proof</CardDescription>
          </CardHeader>
          <CardContent>
            {!links.length && <EmptyState title="No shared identifiers" description="No other borrower shares a phone, email, address, device or bank account on file. The graph grows as identifiers are confirmed (e.g. via loan requests)." />}
            {links.map((l, i) => (
              <div key={i} className="doc-row">
                <div className="doc-info">
                  <Link to={`/borrower/${l.borrower_id}`}><b>{l.borrower_name || l.borrower_id}</b></Link>
                  <small>via {l.via.identifier_type}: {l.via.value} · {l.via.confidence} confidence</small>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setInspected({ ...l.via, peer: l })}>Why?</Button>
              </div>
            ))}
            {inspected && (
              <div className="review-prev" style={{ marginTop: 12 }}>
                <b>WHAT:</b> {inspected.peer.borrower_name} shares {inspected.identifier_type} <code>{inspected.value}</code><br />
                <b>WHY:</b> identical identifier value stored for both borrowers<br />
                <b>EVIDENCE:</b> borrower profile records · {inspected.linked_count} borrower(s) share it<br />
                <b>CONFIDENCE:</b> {inspected.confidence} · <b>TYPE:</b> observed fact (not inference)<br />
                <span style={{ color: "var(--warning)" }}>Shared identifiers indicate network exposure, not fraud. Requires review.</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Path finder</CardTitle><CardDescription>Real stored relationships only · max 3 hops</CardDescription></CardHeader>
          <CardContent>
            <div style={{ display: "flex", gap: 8 }}>
              <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="Target borrower ID" className="filter-search-input" style={{ flex: 1 }} />
              <Button variant="secondary" size="sm" disabled={pathBusy} onClick={runPath}>{pathBusy ? "…" : "Find path"}</Button>
            </div>
            {path && (
              <div style={{ marginTop: 12 }}>
                {!path.path.length
                  ? <EmptyState title="No path" description={path.message} />
                  : path.path.map((h, i) => (
                    <div key={i} className="audit-row">
                      <div><Link to={`/borrower/${h.from}`}><b>{h.from}</b></Link>
                        <span style={{ color: "var(--text-muted)" }}> —[{h.relationship}: {h.value}]→ </span>
                        <Link to={`/borrower/${h.to}`}><b>{h.to}</b></Link></div>
                      <small style={{ color: "var(--text-muted)" }}>{h.confidence}</small>
                    </div>
                  ))}
              </div>
            )}
            <div style={{ marginTop: 16 }}>
              <Button variant="ghost" size="sm" disabled={guest} onClick={openCase}>＋ Open investigation case</Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {hoodEdges.length > 0 && (
        <Card style={{ marginTop: 16 }}>
          <CardHeader><CardTitle>Direct edges</CardTitle><CardDescription>Your node in the live graph</CardDescription></CardHeader>
          <CardContent>
            {hoodEdges.slice(0, 12).map((e, i) => (
              <div key={i} className="audit-row">
                <div><b>{e.relationship}</b> <span style={{ color: "var(--text-muted)" }}>→ {e.target}</span></div>
                <Badge variant="LOW">{e.confidence}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
