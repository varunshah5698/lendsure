import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useAuth, guardLender } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { grievances, officers } from "../lib/api";
import { formatDate } from "../lib/dates";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonCard } from "../components/ui/Skeleton";

/** Staff investigation view: assign, note-take, resolve, escalate. */
export default function GrievanceDetail() {
  const { id } = useParams();
  const { session } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [note, setNote] = useState("");
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignPhone, setAssignPhone] = useState("");
  const [staff, setStaff] = useState([]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [g, os] = await Promise.all([
        grievances.get(id, session.token),
        officers.list(session.token).catch(() => []),
      ]);
      setData(g);
      setStaff(os);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [id, session?.token]);

  useEffect(() => { load(); }, [load]);

  const act = async (fn, okMsg) => {
    if (!guardLender(session, toast)) return;
    try {
      setData(await fn());
      toast.success(okMsg);
    } catch (e) { toast.error(e.message); }
  };

  const addNote = () => {
    if (note.trim().length < 2) return toast.error("Write the investigation note first");
    act(() => grievances.note(id, note.trim(), session.token).then(() => { setNote(""); return grievances.get(id, session.token); }), "Note added to the case file");
  };

  const assign = () => act(
    () => grievances.assign(id, assignPhone.replace(/\D/g, ""), session.token).then(() => { setAssignOpen(false); setAssignPhone(""); return grievances.get(id, session.token); }),
    "Investigator assigned");

  if (loading) return <div><PageHeader title="Loading…" /><SkeletonCard /><SkeletonCard /></div>;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;
  const closed = data.status === "RESOLVED" || data.status === "CLOSED";

  return (
    <div>
      <PageHeader
        title={`${data.ticket_id} · ${data.subject}`}
        description={`${data.name} · ${data.phone}${data.borrower_id ? ` · borrower ${data.borrower_id}` : ""} · ${data.category.replace(/_/g, " ")} · filed ${formatDate(data.created_at)}`}
        actions={<Badge variant={data.status === "OPEN" ? "MEDIUM" : closed ? "APPROVE" : "MANUAL_REVIEW"}>{data.status.replace(/_/g, " ")}</Badge>}
      />
      <Card style={{ marginBottom: 16 }}>
        <CardHeader><CardTitle>Complaint</CardTitle>
          <CardDescription>Assigned to {data.assigned_to || "nobody yet"}{data.resolved_at ? ` · resolved ${formatDate(data.resolved_at)}` : ""}</CardDescription></CardHeader>
        <CardContent>
          <p style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>{data.description || "No description provided."}</p>
          <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
            <Button variant="secondary" size="sm" onClick={() => setAssignOpen(true)}>Assign investigator</Button>
            {!closed && data.status === "OPEN" && (
              <Button variant="secondary" size="sm" onClick={() => act(() => grievances.setStatus(id, "IN_REVIEW", "", session.token), "Moved to investigation")}>Start investigation</Button>
            )}
            {!closed && (
              <>
                <Button variant="secondary" size="sm" onClick={() => act(() => grievances.setStatus(id, "ESCALATED", "", session.token), "Escalated to a senior reviewer")}>Escalate</Button>
                <Button variant="primary" size="sm" onClick={() => act(() => grievances.setStatus(id, "RESOLVED", "", session.token), "Complaint resolved")}>Resolve</Button>
              </>
            )}
            {closed && (
              <Button variant="secondary" size="sm" onClick={() => act(() => grievances.setStatus(id, "OPEN", "", session.token), "Complaint reopened")}>Reopen</Button>
            )}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Investigation notes</CardTitle><CardDescription>Case file — visible to the borrower on the tracking page</CardDescription></CardHeader>
        <CardContent>
          {(data.notes || []).map((n) => (
            <div key={n.id} className="audit-row">
              <div>{n.note}<br /><small style={{ color: "var(--text-muted)" }}>{n.actor} · {formatDate(n.created_at)}</small></div>
            </div>
          ))}
          {!closed && (
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <input value={note} onChange={(e) => setNote(e.target.value)} className="filter-search-input" placeholder="Add an investigation note…" style={{ flex: 1 }} />
              <Button variant="primary" size="sm" onClick={addNote}>Add note</Button>
            </div>
          )}
        </CardContent>
      </Card>
      <Modal open={assignOpen} onClose={() => setAssignOpen(false)} title="Assign investigator"
        actions={<><Button variant="ghost" onClick={() => setAssignOpen(false)}>Cancel</Button>
          <Button variant="primary" onClick={assign}>Assign</Button></>}>
        <label className="review-note-label">Officer mobile number</label>
        <input value={assignPhone} onChange={(e) => setAssignPhone(e.target.value.replace(/\D/g, ""))} className="filter-search-input" placeholder="10-digit mobile" maxLength={10} list="grv-officers" />
        <datalist id="grv-officers">
          {staff.map((o) => <option key={o.id} value={o.phone}>{o.name} · {o.city}</option>)}
        </datalist>
      </Modal>
    </div>
  );
}
