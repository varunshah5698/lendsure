import { useState, useEffect, useCallback, Fragment } from "react";
import { useAuth, guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { cases, officers } from "../lib/api";
import { formatDate } from "../lib/dates";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { SkeletonTable } from "../components/ui/Skeleton";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";

export default function Cases() {
  const { session } = useAuth();
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [bid, setBid] = useState("");
  const [desc, setDesc] = useState("");
  const [assignId, setAssignId] = useState(null);
  const [assignPhone, setAssignPhone] = useState("");
  const [transferId, setTransferId] = useState(null);
  const [toCity, setToCity] = useState("");
  const [transferNote, setTransferNote] = useState("");
  const [historyId, setHistoryId] = useState(null);
  const [history, setHistory] = useState([]);
  const [queue, setQueue] = useState([]);
  const [showQueue, setShowQueue] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [cs, os] = await Promise.all([
        cases.list({ status: filter || undefined }, session.token),
        officers.list(session.token).catch(() => []),
      ]);
      setRows(cs);
      setStaff(os);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [filter, session?.token]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!guardLender(session, toast)) return;
    if (title.trim().length < 4) return toast.error("Give the case a title");
    try {
      await cases.create({
        title: title.trim(),
        borrower_id: bid.trim(),
        evidence: desc.trim() ? { description: desc.trim() } : {},
      }, session.token);
      toast.success("Case opened");
      setOpen(false);
      setTitle("");
      setBid("");
      setDesc("");
      load();
    } catch (e) { toast.error("Create failed: " + e.message); }
  };

  const resolve = async (id) => {
    if (!guardLender(session, toast)) return;
    try {
      await cases.resolve(id, session.token);
      toast.success("Case resolved");
      load();
    } catch (e) { toast.error("Resolve failed: " + e.message); }
  };

  const assign = async () => {
    if (!guardLender(session, toast)) return;
    try {
      await cases.assign(assignId, assignPhone.replace(/\D/g, ""), session.token);
      toast.success("Case assigned to the territory officer");
      setAssignId(null);
      setAssignPhone("");
      load();
    } catch (e) { toast.error("Assign failed: " + e.message); }
  };

  const requestTransfer = async () => {
    if (!guardLender(session, toast)) return;
    if (toCity.trim().length < 2) return toast.error("Enter the destination city");
    try {
      await cases.transferRequest(transferId, { to_city: toCity.trim(), note: transferNote.trim() }, session.token);
      toast.success("Transfer requested — awaiting review");
      setTransferId(null);
      setToCity("");
      setTransferNote("");
      load();
    } catch (e) { toast.error("Request failed: " + e.message); }
  };

  const reviewTransfer = async (id, decision) => {
    if (!guardLender(session, toast)) return;
    const assignTo = decision === "APPROVE" ? window.prompt("Assign to officer phone in the new city (optional, blank to leave unassigned):", "") || "" : "";
    try {
      await cases.transferReview(id, { decision, assign_to: assignTo.replace(/\D/g, ""), note: "" }, session.token);
      toast.success(decision === "APPROVE" ? "Case transferred" : "Transfer rejected");
      load();
      if (showQueue) openQueue();
    } catch (e) { toast.error("Review failed: " + e.message); }
  };

  const openQueue = async () => {
    try {
      setQueue(await cases.transferQueue({ status: "REQUESTED" }, session.token));
      setShowQueue(true);
    } catch (e) { toast.error("Queue failed: " + e.message); }
  };

  const openHistory = async (id) => {
    if (historyId === id) { setHistoryId(null); return; }
    try {
      setHistory(await cases.transfers(id, session.token));
      setHistoryId(id);
    } catch (e) { toast.error("History failed: " + e.message); }
  };

  const officerName = (phone) => staff.find((o) => o.phone === phone)?.name || phone || "—";
  const guest = isGuest(session);
  const pendingCount = rows.filter((c) => c.transfer_status === "REQUESTED").length;

  return (
    <div>
      <PageHeader
        title="Investigation Cases"
        description="Graph and fraud findings become tracked, resolvable cases — with territory assignment and cross-city transfers"
        actions={<>
          <Button variant="secondary" size="sm" onClick={openQueue}>
            Transfer inbox{pendingCount ? ` (${pendingCount})` : ""}
          </Button>
          <Button variant="primary" size="sm" disabled={guest} title={guest ? "Sign in with Phone OTP" : "Open a case"} onClick={() => setOpen(true)}>＋ Open case</Button>
        </>}
      />
      <Card padding="sm">
        <div className="filters-row">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="filter-select">
            <option value="">All</option>
            <option value="OPEN">Open</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </div>
        {loading ? <SkeletonTable rows={6} cols={6} /> :
          error ? <ErrorState message={error} onRetry={load} /> :
          !rows.length ? <EmptyState title="No cases" description="Create one from a graph finding or fraud signal." /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Case</th><th>Borrower</th><th>Assignee</th><th>Transfer</th><th>Status</th><th>Opened</th><th></th></tr></thead>
              <tbody>
                {rows.map((c) => (
                  <Fragment key={c.id}>
                    <tr key={c.id}>
                      <td><b>#{c.id} {c.title}</b> <span style={{ color: "var(--text-muted)", fontSize: 12 }}>· {c.kind}</span></td>
                      <td>{c.borrower_id || "—"}</td>
                      <td style={{ fontSize: 12 }}>{c.assigned_to ? officerName(c.assigned_to) : <span style={{ color: "var(--text-muted)" }}>Unassigned</span>}</td>
                      <td>
                        {c.transfer_status === "REQUESTED"
                          ? <Badge variant="MANUAL_REVIEW">TRANSFER REQUESTED</Badge>
                          : c.transfer_status === "TRANSFERRED"
                            ? <Badge variant="APPROVE">TRANSFERRED{c.city ? ` → ${c.city}` : ""}</Badge>
                            : <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{c.city || "—"}</span>}
                      </td>
                      <td><Badge variant={c.status === "OPEN" ? "MEDIUM" : "APPROVE"}>{c.status}</Badge></td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDate(c.created_at)} · {c.created_by}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        {c.status === "OPEN" && !guest && (
                          <>
                            <Button variant="ghost" size="sm" onClick={() => { setAssignId(c.id); setAssignPhone(c.assigned_to || ""); }}>Assign</Button>
                            {c.transfer_status !== "REQUESTED" && c.transfer_status !== "TRANSFERRED" && (
                              <Button variant="ghost" size="sm" onClick={() => { setTransferId(c.id); setToCity(""); setTransferNote(""); }}>Transfer</Button>
                            )}
                            {c.transfer_status === "REQUESTED" && (
                              <>
                                <Button variant="secondary" size="sm" onClick={() => reviewTransfer(c.id, "APPROVE")}>Approve move</Button>
                                <Button variant="ghost" size="sm" onClick={() => reviewTransfer(c.id, "REJECT")}>Reject</Button>
                              </>
                            )}
                            <Button variant="ghost" size="sm" onClick={() => openHistory(c.id)}>History</Button>
                            <Button variant="ghost" size="sm" onClick={() => resolve(c.id)}>Resolve</Button>
                          </>
                        )}
                      </td>
                    </tr>
                    {historyId === c.id && (
                      <tr key={`${c.id}-h`}>
                        <td colSpan={7} style={{ background: "var(--surface-hover)", fontSize: 12 }}>
                          {history.length ? history.map((t) => (
                            <div key={t.id} style={{ padding: "4px 0" }}>
                              <b>{t.status}</b> · {t.from_city || "?"} → <b>{t.to_city}</b> · requested by {t.requested_by}
                              {t.decided_by ? ` · decided by ${t.decided_by}` : ""} · {formatDate(t.created_at)}
                              {t.note ? <div style={{ color: "var(--text-muted)" }}>{t.note}</div> : null}
                            </div>
                          )) : <span style={{ color: "var(--text-muted)" }}>No transfers recorded for this case.</span>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="Open investigation case"
        actions={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" onClick={create}>Open case</Button></>}>
        <label className="review-note-label">Title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="filter-search-input" placeholder="e.g. Shared device across 3 borrowers" />
        <label className="review-note-label" style={{ marginTop: 10 }}>Borrower ID (optional)</label>
        <input value={bid} onChange={(e) => setBid(e.target.value)} className="filter-search-input" placeholder="e.g. B10003" />
        <label className="review-note-label" style={{ marginTop: 10 }}>Details (optional)</label>
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)} className="filter-search-input"
          rows={4} placeholder="What did you find? Signals, names, dates, amounts…"
          style={{ resize: "vertical" }} />
      </Modal>

      <Modal open={assignId !== null} onClose={() => setAssignId(null)} title="Assign to territory officer"
        actions={<><Button variant="ghost" onClick={() => setAssignId(null)}>Cancel</Button>
          <Button variant="primary" onClick={assign}>Assign</Button></>}>
        <label className="review-note-label">Officer mobile number</label>
        <input value={assignPhone} onChange={(e) => setAssignPhone(e.target.value.replace(/\D/g, ""))} className="filter-search-input" placeholder="10-digit mobile" maxLength={10} list="officer-phones" />
        <datalist id="officer-phones">
          {staff.map((o) => <option key={o.id} value={o.phone}>{o.name} · {o.city}</option>)}
        </datalist>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>Pick the officer who owns the borrower's city.</p>
      </Modal>

      <Modal open={transferId !== null} onClose={() => setTransferId(null)} title="Request cross-city transfer"
        actions={<><Button variant="ghost" onClick={() => setTransferId(null)}>Cancel</Button>
          <Button variant="primary" onClick={requestTransfer}>Send request</Button></>}>
        <label className="review-note-label">Destination city (borrower's city)</label>
        <input value={toCity} onChange={(e) => setToCity(e.target.value)} className="filter-search-input" placeholder="e.g. Pune" />
        <label className="review-note-label" style={{ marginTop: 10 }}>Reason</label>
        <textarea value={transferNote} onChange={(e) => setTransferNote(e.target.value)} className="filter-search-input"
          rows={3} placeholder="e.g. Borrower relocated; needs local field visit" style={{ resize: "vertical" }} />
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>A reviewer approves the move and picks the receiving officer. Nothing moves silently — the full trail stays on the case.</p>
      </Modal>

      <Modal open={showQueue} onClose={() => setShowQueue(false)} title="Transfer inbox — pending handoffs">
        {!queue.length ? <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No pending transfer requests.</p> : (
          <div>
            {queue.map((t) => (
              <div key={t.id} className="audit-row">
                <div>
                  <b>Case #{t.case_id}</b> {t.case_title ? `· ${t.case_title}` : ""}<br />
                  <small style={{ color: "var(--text-muted)" }}>
                    {t.from_city || "?"} → <b>{t.to_city}</b> · requested by {t.requested_by} · {formatDate(t.created_at)}
                    {t.note ? ` · ${t.note}` : ""}
                  </small>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <Button variant="secondary" size="sm" onClick={() => reviewTransfer(t.case_id, "APPROVE")}>Approve</Button>
                  <Button variant="ghost" size="sm" onClick={() => reviewTransfer(t.case_id, "REJECT")}>Reject</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
