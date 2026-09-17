import { useState, useEffect, useCallback } from "react";
import { useAuth, guardLender } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { officers } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { SkeletonTable } from "../components/ui/Skeleton";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";
import Icon from "../components/ui/Icon";

export default function Officers() {
  const { session } = useAuth();
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", city: "" });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setRows(await officers.list(session.token));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [session?.token]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!guardLender(session, toast)) return;
    if (form.name.trim().length < 2) return toast.error("Enter the officer's name");
    if (!/^\d{10}$/.test(form.phone.replace(/\D/g, ""))) return toast.error("Enter a 10-digit mobile number");
    if (form.city.trim().length < 2) return toast.error("Enter the assigned city");
    try {
      await officers.create({ ...form, phone: form.phone.replace(/\D/g, "") }, session.token);
      toast.success("Officer saved — borrowers in that city default to them");
      setOpen(false);
      setForm({ name: "", phone: "", city: "" });
      load();
    } catch (e) { toast.error("Save failed: " + e.message); }
  };

  const toggle = async (o) => {
    if (!guardLender(session, toast)) return;
    try {
      await officers.update(o.id, { active: o.active ? 0 : 1 }, session.token);
      toast.success(o.active ? "Officer deactivated" : "Officer reactivated");
      load();
    } catch (e) { toast.error("Update failed: " + e.message); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Governance"
        title="Recovery Officers"
        description="Each officer owns one city. Borrowers from that city default to them, and cross-city cases route through transfer requests."
        actions={<Button variant="primary" size="sm" onClick={() => setOpen(true)}>＋ Add officer</Button>}
      />
      <Card padding="sm">
        {loading ? <SkeletonTable rows={5} cols={5} /> :
          error ? <ErrorState message={error} onRetry={load} /> :
          !rows.length ? <EmptyState title="No officers yet" description="Add your first recovery officer with their assigned city." /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Officer</th><th>Territory</th><th>Open cases</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {rows.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <div className="borrower-cell">
                        <div className="borrower-avatar">{(o.name || "?").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}</div>
                        <div><div className="borrower-name">{o.name}</div><div className="borrower-id">{o.phone}</div></div>
                      </div>
                    </td>
                    <td><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Icon name="pin" size={13} /> <b>{o.city}</b></span></td>
                    <td><span className="trust-value">{o.open_cases}</span></td>
                    <td><Badge variant={o.active ? "APPROVE" : "MANUAL_REVIEW"}>{o.active ? "ACTIVE" : "INACTIVE"}</Badge></td>
                    <td><Button variant="ghost" size="sm" onClick={() => toggle(o)}>{o.active ? "Deactivate" : "Reactivate"}</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Add recovery officer"
        actions={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" onClick={save}>Save officer</Button></>}>
        <label className="review-note-label">Full name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="filter-search-input" placeholder="e.g. Ravi Patil" />
        <label className="review-note-label" style={{ marginTop: 10 }}>Mobile number (10-digit)</label>
        <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value.replace(/\D/g, "") })} className="filter-search-input" placeholder="e.g. 9811111111" maxLength={10} />
        <label className="review-note-label" style={{ marginTop: 10 }}>Assigned city (territory)</label>
        <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="filter-search-input" placeholder="e.g. Mumbai" />
      </Modal>
    </div>
  );
}
