import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { borrowers, inr, officers } from "../lib/api";
import { downloadCSV } from "../lib/export";
import SearchInput from "../components/ui/SearchInput";
import Avatar from "../components/ui/Avatar";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Icon from "../components/ui/Icon";
import EmptyState from "../components/ui/EmptyState";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonTable } from "../components/ui/Skeleton";
import "./Borrowers.css";

const INIT_FILTERS = { q: "", risk: "all", verification: "all", city: "all", employment: "all", sort: "trust_desc", page: 1 };

export default function Borrowers({ searchQuery = "" }) {
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [filters, setFilters] = useState(INIT_FILTERS);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [cities, setCities] = useState([]);
  const [employments, setEmployments] = useState([]);
  const [territory, setTerritory] = useState(null);

  // Recovery officers open on their assigned city by default.
  useEffect(() => {
    officers.me(session.token)
      .then((o) => {
        setTerritory(o);
        setFilters((prev) => (prev.city === "all" ? { ...prev, city: o.city, page: 1 } : prev));
      })
      .catch(() => {});
  }, [session?.token]);

  // Sync global topbar search into the local query filter
  useEffect(() => {
    setFilters((prev) => (prev.q === searchQuery ? prev : { ...prev, q: searchQuery, page: 1 }));
  }, [searchQuery]);

  const load = useCallback(async (facets = false) => {
    try {
      setLoading(true);
      setError(null);
      const d = await borrowers.list(filters, session.token);
      setData(d);
      if (facets) {
        setCities(d.facets?.cities || []);
        setEmployments(d.facets?.employments || []);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filters, session?.token]);

  const firstLoad = useRef(true);
  useEffect(() => {
    const t = setTimeout(() => {
      load(firstLoad.current);
      firstLoad.current = false;
    }, 300);
    return () => clearTimeout(t);
  }, [filters, load]);

  const updateFilter = (key, val) => setFilters((prev) => ({ ...prev, [key]: val, page: 1 }));

  const activeFilters = Object.entries(filters).filter(([k, v]) => v && v !== "all" && v !== "" && k !== "page" && k !== "sort");

  if (error) return <ErrorState message={error} onRetry={() => load(true)} />;

  return (
    <div>
      <PageHeader
        title="Borrowers"
        description={territory
          ? `My territory: ${territory.city} · showing local borrowers first (switch to All cities anytime)`
          : `Search, filter and sort the full ${data?.total?.toLocaleString() || "..."}-borrower portfolio`}
        actions={data?.rows?.length ? (
          <Button variant="secondary" size="sm" onClick={() => {
            downloadCSV("borrowers.csv", data.rows);
            toast.success("Exported current page to CSV");
          }}> <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Icon name="download" size={14} /> Export CSV</span></Button>
        ) : null}
      />

      <Card padding="sm">
        <div className="filters-row">
          <SearchInput
            value={filters.q}
            onChange={(v) => updateFilter("q", v)}
            placeholder="Search name, ID, city…"
          />
          <select value={filters.risk} onChange={(e) => updateFilter("risk", e.target.value)} className="filter-select">
            <option value="all">All risks</option>
            <option>LOW</option><option>MEDIUM</option><option>HIGH</option>
          </select>
          <select value={filters.verification} onChange={(e) => updateFilter("verification", e.target.value)} className="filter-select">
            <option value="all">All verification</option>
            <option value="verified">Verified</option>
            <option value="needs_review">Needs review</option>
            <option value="suspicious">Suspicious</option>
          </select>
          <select value={filters.city} onChange={(e) => updateFilter("city", e.target.value)} className="filter-select">
            <option value="all">All cities</option>
            {cities.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select value={filters.employment} onChange={(e) => updateFilter("employment", e.target.value)} className="filter-select">
            <option value="all">All employment</option>
            {employments.map((e) => <option key={e}>{e}</option>)}
          </select>
          <select value={filters.sort} onChange={(e) => updateFilter("sort", e.target.value)} className="filter-select">
            <option value="trust_desc">Trust ↓</option>
            <option value="trust_asc">Trust ↑</option>
            <option value="requested_desc">Requested ↓</option>
            <option value="requested_asc">Requested ↑</option>
            <option value="name_asc">Name A–Z</option>
          </select>
        </div>

        {activeFilters.length > 0 && (
          <div className="active-filters">
            {activeFilters.map(([k, v]) => (
              <span key={k} className="filter-chip">
                {k}: {v}
                <button className="filter-chip-x" onClick={() => updateFilter(k, k === "q" ? "" : "all")}>×</button>
              </span>
            ))}
            <button className="filter-clear" onClick={() => setFilters(INIT_FILTERS)}>Clear all</button>
          </div>
        )}

        {loading ? (
          <SkeletonTable rows={8} cols={8} />
        ) : !data?.rows?.length ? (
          <EmptyState title="No borrowers found" description="Try adjusting your filters or search query." />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Borrower</th>
                  <th>Age</th>
                  <th>City</th>
                  <th>Employment</th>
                  <th>Income</th>
                  <th>Requested</th>
                  <th>Trust</th>
                  <th>Risk</th>
                  <th>Verification</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.borrower_id} className="clickable" onClick={() => navigate(`/borrower/${r.borrower_id}`)}>
                    <td>
                      <div className="borrower-cell">
                        <Avatar name={r.name} />
                        <div><div className="borrower-name">{r.name}{String(r.borrower_id).startsWith("SIM-") && <span title="Simulation record — excluded from portfolio metrics" style={{ marginLeft: 6, fontSize: 10, fontWeight: 800, color: "#22d3ee", border: "1px solid rgba(34,211,238,.5)", borderRadius: 4, padding: "1px 5px" }}>SIMULATION</span>}</div><div className="borrower-id">{r.borrower_id}</div></div>
                      </div>
                    </td>
                    <td>{r.age}</td>
                    <td>{r.city}</td>
                    <td style={{ textTransform: "capitalize" }}>{r.employment}</td>
                    <td>{inr(r.income)}</td>
                    <td>{inr(r.requested)}</td>
                    <td><span className="trust-value">{r.trust ?? "—"}</span></td>
                    <td><Badge variant={r.risk}>{r.risk || "—"}</Badge></td>
                    <td><Badge variant={r.verification}>{(r.verification || "").replace(/_/g, " ")}</Badge></td>
                    <td style={{ color: "var(--text-muted)" }}>→</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && (
          <div className="pagination">
            <Button variant="secondary" size="sm" disabled={data.page <= 1} onClick={() => setFilters((p) => ({ ...p, page: p.page - 1 }))}>← Prev</Button>
            <span className="pagination-info">Page {data.page} of {Math.max(1, Math.ceil(data.total / 12))} · {data.total?.toLocaleString()} borrowers</span>
            <Button variant="secondary" size="sm" disabled={data.page >= Math.ceil(data.total / 12)} onClick={() => setFilters((p) => ({ ...p, page: p.page + 1 }))}>Next →</Button>
          </div>
        )}
      </Card>
    </div>
  );
}
