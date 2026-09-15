"""Audit hash chain, migration ledger, grievance portal."""
import app as app_module
from lendsure.notify import audit as naudit, verify_audit_chain


def _conn():
    return app_module.db()


def test_audit_chain_verifies_and_detects_tamper(client):
    conn = _conn()
    try:
        for i in range(3):
            naudit(conn, "B90001", None, "test", "probe", {"i": i})
        conn.commit()
        ok = verify_audit_chain(conn)
        assert ok["ok"] is True and ok["checked"] >= 3
        row = conn.execute("SELECT MIN(id) i FROM ls_audit").fetchone()["i"]
        conn.execute("UPDATE ls_audit SET detail='tampered' WHERE id=?", (row,))
        bad = verify_audit_chain(conn)
        assert bad["ok"] is False and bad["bad_id"] == row
    finally:
        conn.close()


def test_migrations_recorded_and_idempotent(client):
    conn = _conn()
    try:
        n1 = conn.execute("SELECT COUNT(*) c FROM ls_migrations").fetchone()["c"]
    finally:
        conn.close()
    assert n1 > 0
    app_module.init_db()  # second boot must be a no-op, never an error
    conn = _conn()
    try:
        n2 = conn.execute("SELECT COUNT(*) c FROM ls_migrations").fetchone()["c"]
    finally:
        conn.close()
    assert n1 == n2


def test_failed_migration_rolls_back(client):
    from app import _apply_migration
    conn = _conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _mig_probe (id INTEGER PRIMARY KEY, v TEXT)")
        conn.commit()
        try:
            _apply_migration(conn, "probe-bad-sql", "ALTER TABLE _mig_probe ADD COLUMN v TEXT; THIS IS NOT SQL;")
            raise AssertionError("should have raised")
        except Exception:
            pass
        cols = [r[1] for r in conn.execute("PRAGMA table_info(_mig_probe)").fetchall()]
        assert cols == ["id", "v"], cols  # partial ALTER rolled back
        assert conn.execute("SELECT COUNT(*) c FROM ls_migrations WHERE name='probe-bad-sql'").fetchone()["c"] == 0
    finally:
        conn.close()


def test_grievance_public_flow_and_staff_gates(client, lender, guest):
    r = client.post("/api/ls/grievances",
                    json={"name": "Asha", "phone": "9833333333", "category": "collection",
                          "subject": "Rude recovery calls", "description": "Called six times"})
    assert r.status_code == 200
    ticket = r.json()["ticket_id"]
    assert ticket.startswith("GRV-")
    r = client.get(f"/api/ls/grievances/track?ticket_id={ticket}&phone=9833333333")
    assert r.status_code == 200 and r.json()["status"] == "OPEN"
    assert guest.get("/api/ls/grievances").status_code == 403
    gid = r.json()["id"]
    r = lender.post(f"/api/ls/grievances/{gid}/status",
                    json={"status": "IN_REVIEW", "note": "looking"})
    assert r.status_code == 200 and r.json()["status"] == "IN_REVIEW"
    r = lender.post(f"/api/ls/grievances/{gid}/status", json={"status": "RESOLVED"})
    assert r.json()["status"] == "RESOLVED"


def test_officer_territory_default(client, lender):
    lender.post("/api/ls/officers",
                json={"name": "T Officer", "phone": "9844444444", "city": "Mumbai"})
    r = lender.get("/api/ls/officers/me")
    assert r.status_code == 404  # lender login is not an officer phone
    t = lender.get("/api/ls/territory/summary").json()
    assert t["city"] == "ALL" and t["borrowers"] >= 1
