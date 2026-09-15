"""Graph intelligence over REAL stored data.

The graph is relational-backed: nodes/edges are computed from identifier
columns (phone, email, address, device, bank account) actually stored on
borrower rows — plus when/how each identifier was observed (profile import
vs. loan-request confirmation events). Nothing is hardcoded; an empty
identifier column means no edge, reported honestly.

Safety: shared identifiers are network *exposure*, never fraud proof.
Every edge carries type OBSERVED_FACT with source + confidence, and the UI
must use "shared identifier / requires review" language.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ls", tags=["graph"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def _need(authorization: Optional[str], x_api_key: Optional[str], *perms: str) -> str:
    from .api import require_perm
    return require_perm(authorization, x_api_key, *perms)


ID_FIELDS = (
    ("phone", "USES_PHONE", "high", "Borrower uses phone number"),
    ("email", "USES_EMAIL", "high", "Borrower uses email address"),
    ("address_line", "LIVES_AT_ADDRESS", "medium", "Borrower address on file"),
    ("device_id", "USES_DEVICE", "medium", "Borrower device identifier"),
    ("bank_account", "BORROWER_OWNS_BANK_ACCOUNT", "high", "Borrower bank account"),
)


def _borrower_identifiers(conn, bid: str) -> dict:
    row = conn.execute(
        "SELECT borrower_id, name, city, phone, email, address_line, device_id, bank_account,"
        " created_at FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone()
    if not row:
        raise HTTPException(404, "Borrower not found")
    return dict(row)


def _identifier_owners(conn, field: str, value: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        f"SELECT borrower_id, name, city FROM ls_borrowers WHERE {field}=? AND {field}!=''",
        (value,)).fetchall()]


def _identifier_source(conn, bid: str, field: str) -> dict:
    """WHEN + SOURCE from the attribute-change event log (observed facts)."""
    rows = conn.execute(
        "SELECT actor, data, created_at FROM ls_events WHERE entity='borrower' AND entity_id=?"
        " AND type='BorrowerAttributeChanged' ORDER BY id", (bid,)).fetchall()
    for r in rows:
        try:
            if json.loads(r["data"] or "{}").get("field") == field:
                return {"source": "loan_request_confirmation", "actor": r["actor"],
                        "observed_at": r["created_at"]}
        except Exception:
            continue
    return {"source": "borrower_profile", "actor": "system", "observed_at": None}


def _node_borrower(conn, bid: str) -> dict:
    b = _borrower_identifiers(conn, bid)
    risk = conn.execute(
        "SELECT risk_level, trust_score FROM ls_analyses WHERE borrower_id=? ORDER BY id DESC LIMIT 1",
        (bid,)).fetchone()
    return {"id": f"borrower:{bid}", "kind": "borrower", "label": b["name"],
            "borrower_id": bid, "city": b["city"],
            "risk_level": risk["risk_level"] if risk else None,
            "trust_score": risk["trust_score"] if risk else None}


def neighborhood(conn, bid: str, hops: int = 2, max_nodes: int = 500,
                 max_edges: int = 1500) -> dict:
    """Bounded BFS borrower <-> identifier bipartite expansion."""
    hops = max(1, min(hops, 3))
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edge: set[tuple] = set()

    def add_edge(src: str, rel: str, dst: str, kind: str, confidence: str,
                 evidence: dict):
        if len(edges) >= max_edges:
            return False
        key = (src, rel, dst)
        if key in seen_edge:
            return True
        seen_edge.add(key)
        edges.append({"source": src, "target": dst, "relationship": rel,
                      "fact_type": "OBSERVED_FACT", "confidence": confidence,
                      "evidence": evidence})
        return True

    center = _node_borrower(conn, bid)
    nodes[center["id"]] = center
    frontier = [bid]
    for _ in range(hops):
        nxt: list[str] = []
        for cbid in frontier:
            if len(nodes) >= max_nodes:
                break
            b = _borrower_identifiers(conn, cbid)
            for field, rel, conf, why in ID_FIELDS:
                val = (b.get(field) or "").strip()
                if not val:
                    continue
                nid = f"{field}:{val}"
                if nid not in nodes:
                    if len(nodes) >= max_nodes:
                        break
                    nodes[nid] = {"id": nid, "kind": "identifier",
                                  "identifier_type": field, "label": val}
                srcinfo = _identifier_source(conn, cbid, field)
                if not add_edge(f"borrower:{cbid}", rel, nid, "identifier", conf, {
                        "what": why, "why": f"Same {field} value stored for multiple borrowers",
                        "value": val, "when": srcinfo["observed_at"],
                        "source": srcinfo["source"], "recorded_by": srcinfo["actor"]}):
                    break
                for o in _identifier_owners(conn, field, val):
                    oid = f"borrower:{o['borrower_id']}"
                    if oid not in nodes:
                        if len(nodes) >= max_nodes:
                            break
                        nodes[oid] = {"id": oid, "kind": "borrower",
                                      "label": o["name"], "borrower_id": o["borrower_id"],
                                      "city": o["city"]}
                    if not add_edge(oid, rel, nid, "identifier", conf, {
                            "what": why, "why": f"Same {field} value stored for multiple borrowers",
                            "value": val, "when": None, "source": "borrower_profile",
                            "recorded_by": "system"}):
                        break
                    if o["borrower_id"] != cbid and o["borrower_id"] not in frontier + nxt:
                        nxt.append(o["borrower_id"])
        frontier = nxt
        if not frontier:
            break
    # annotate borrower nodes with risk (single batched pass)
    for n in nodes.values():
        if n["kind"] == "borrower" and n.get("risk_level") is None and n["id"] != center["id"]:
            r = conn.execute("SELECT risk_level, trust_score FROM ls_analyses WHERE borrower_id=? "
                             "ORDER BY id DESC LIMIT 1", (n["borrower_id"],)).fetchone()
            if r:
                n["risk_level"], n["trust_score"] = r["risk_level"], r["trust_score"]
    return {"center": center["id"], "nodes": list(nodes.values()), "edges": edges,
            "truncated": len(nodes) >= max_nodes or len(edges) >= max_edges}


def _all_strong_links(conn) -> dict[str, set[str]]:
    """Borrower -> set(borrowers) sharing any strong identifier. Union-find input."""
    adj: dict[str, set[str]] = {}
    for field, _, _, _ in ID_FIELDS:
        rows = conn.execute(
            f"SELECT {field} v, GROUP_CONCAT(borrower_id) ids FROM ls_borrowers "
            f"WHERE {field}!='' AND {field} IS NOT NULL GROUP BY {field} HAVING COUNT(*)>1"
        ).fetchall()
        for r in rows:
            ids = r["ids"].split(",")
            for a in ids:
                adj.setdefault(a, set()).update(i for i in ids if i != a)
    return adj


@router.get("/borrowers/{bid}/graph")
def borrower_graph(bid: str, hops: int = 2, max_nodes: int = 500, max_edges: int = 1500,
                   authorization: Optional[str] = Header(default=None),
                   x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "graph.read")
    t0 = time.time()
    conn = _DB()
    try:
        out = neighborhood(conn, bid, hops, min(max_nodes, 500), min(max_edges, 1500))
        out["query_ms"] = round((time.time() - t0) * 1000, 1)
        out["engine"] = "relational-backed (recomputed live, always in sync)"
        return out
    finally:
        conn.close()


@router.get("/borrowers/{bid}/network-summary")
def network_summary(bid: str, authorization: Optional[str] = Header(default=None),
                    x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "graph.read")
    conn = _DB()
    try:
        b = _borrower_identifiers(conn, bid)
        shared: list[dict] = []
        total_links = 0
        for field, rel, conf, _ in ID_FIELDS:
            val = (b.get(field) or "").strip()
            if not val:
                continue
            owners = [o for o in _identifier_owners(conn, field, val)
                      if o["borrower_id"] != bid]
            if owners:
                total_links += len(owners)
                shared.append({"identifier_type": field, "relationship": rel,
                               "value": val, "confidence": conf,
                               "linked_borrowers": owners[:25],
                               "linked_count": len(owners)})
        return {"borrower_id": bid,
                "identifiers_on_file": sum(1 for f, _, _, _ in ID_FIELDS if (b.get(f) or "").strip()),
                "linked_borrowers": total_links,
                "shared": shared}
    finally:
        conn.close()


class PathIn(BaseModel):
    from_borrower: str = Field(min_length=1, max_length=32)
    to_borrower: str = Field(min_length=1, max_length=32)
    max_hops: int = Field(default=3, ge=1, le=4)


@router.post("/graph/path")
def find_path(body: PathIn, authorization: Optional[str] = Header(default=None),
              x_api_key: Optional[str] = Header(default=None)):
    """BFS over real stored relationships only. No invented paths."""
    _need(authorization, x_api_key, "graph.read")
    if body.from_borrower == body.to_borrower:
        raise HTTPException(422, "Select two different borrowers")
    conn = _DB()
    try:
        _borrower_identifiers(conn, body.from_borrower)
        _borrower_identifiers(conn, body.to_borrower)

        def neighbors(bid: str):
            out = []
            b = _borrower_identifiers(conn, bid)
            for field, rel, conf, _ in ID_FIELDS:
                val = (b.get(field) or "").strip()
                if not val:
                    continue
                for o in _identifier_owners(conn, field, val):
                    if o["borrower_id"] != bid:
                        out.append((o["borrower_id"], rel, field, val, conf))
            return out

        # BFS storing (node, via_edge)
        prev: dict[str, tuple[str | None, dict | None]] = {body.from_borrower: (None, None)}
        frontier = [body.from_borrower]
        depth = {body.from_borrower: 0}
        found = False
        for _ in range(body.max_hops):
            nxt = []
            for cur in frontier:
                for nb, rel, field, val, conf in neighbors(cur):
                    if nb not in prev:
                        prev[nb] = (cur, {"relationship": rel, "identifier_type": field,
                                          "value": val, "confidence": conf,
                                          "fact_type": "OBSERVED_FACT"})
                        depth[nb] = depth[cur] + 1
                        nxt.append(nb)
                        if nb == body.to_borrower:
                            found = True
                            break
                if found:
                    break
            if found or not nxt:
                break
            frontier = nxt
        if not found:
            return {"path": [], "hops": 0, "message": f"No path within {body.max_hops} hops"}
        # reconstruct
        hops, cur = [], body.to_borrower
        while cur != body.from_borrower:
            p, e = prev[cur]
            hops.append({"from": p, "to": cur, **e})
            cur = p
        hops.reverse()
        return {"path": hops, "hops": len(hops),
                "message": f"Connected via {len(hops)} hop(s) of shared identifiers"}
    finally:
        conn.close()


@router.get("/graph/clusters")
def clusters(min_size: int = 2, authorization: Optional[str] = Header(default=None),
             x_api_key: Optional[str] = Header(default=None)):
    """Connected components over shared strong identifiers (union-find)."""
    _need(authorization, x_api_key, "graph.read")
    t0 = time.time()
    conn = _DB()
    try:
        adj = _all_strong_links(conn)
        parent: dict[str, str] = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for a, nbs in adj.items():
            for c in nbs:
                union(a, c)
        groups: dict[str, list[str]] = {}
        for a in adj:
            groups.setdefault(find(a), []).append(a)
        out = []
        for cid, members in groups.items():
            if len(members) < max(2, min_size):
                continue
            # shared attributes + risk concentration (real aggregates)
            shared, seen_pairs = [], set()
            for m in members:
                b = _borrower_identifiers(conn, m)
                for field, _, _, _ in ID_FIELDS:
                    v = (b.get(field) or "").strip()
                    if v:
                        shared.append((field, v))
            from collections import Counter
            top_shared = [{"identifier_type": f, "value": v, "count": c}
                          for (f, v), c in Counter(shared).most_common(5) if c > 1]
            risks = [dict(r) for r in conn.execute(
                "SELECT a.borrower_id, a.risk_level FROM ls_analyses a JOIN "
                "(SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x "
                "ON x.borrower_id=a.borrower_id AND x.m=a.id "
                f"WHERE a.borrower_id IN ({','.join('?' * len(members))})", members).fetchall()]
            by_risk: dict[str, int] = {}
            for r in risks:
                by_risk[r["risk_level"]] = by_risk.get(r["risk_level"], 0) + 1
            names = [dict(r) for r in conn.execute(
                f"SELECT borrower_id, name FROM ls_borrowers WHERE borrower_id IN "
                f"({','.join('?' * len(members))})", members).fetchall()]
            out.append({"cluster_id": cid[:8], "size": len(members), "members": names,
                        "shared_attributes": top_shared,
                        "risk_concentration": by_risk,
                        "note": "Shared identifiers indicate network exposure, not fraud."})
        out.sort(key=lambda c: -c["size"])
        return {"clusters": out[:50], "components_total": len(groups),
                "query_ms": round((time.time() - t0) * 1000, 1)}
    finally:
        conn.close()


@router.get("/graph/stats")
def graph_stats(authorization: Optional[str] = Header(default=None),
                x_api_key: Optional[str] = Header(default=None)):
    """Graph health: counts recomputed live from the relational source of truth."""
    _need(authorization, x_api_key, "graph.read")
    t0 = time.time()
    conn = _DB()
    try:
        borrowers = conn.execute("SELECT COUNT(*) c FROM ls_borrowers").fetchone()["c"]
        with_ids = conn.execute(
            "SELECT COUNT(*) c FROM ls_borrowers WHERE phone!='' OR email!='' OR address_line!=''"
            " OR device_id!='' OR bank_account!=''").fetchone()["c"]
        adj = _all_strong_links(conn)
        edges = sum(len(v) for v in adj.values()) // 2
        linked = len(adj)
        ev = conn.execute("SELECT COUNT(*) c FROM ls_events").fetchone()["c"]
        last_ev = conn.execute("SELECT MAX(created_at) m FROM ls_events").fetchone()["m"]
        return {
            "borrowers": borrowers, "borrowers_with_identifiers": with_ids,
            "linked_borrowers": linked, "identifier_edges": edges,
            "domain_events": ev, "last_event_at": last_ev,
            "sync": {"mode": "relational-backed", "status": "in_sync",
                     "detail": "Graph is recomputed from source tables on every query; no separate store to drift."},
            "query_ms": round((time.time() - t0) * 1000, 1),
        }
    finally:
        conn.close()
