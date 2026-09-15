import { useLocation, useNavigate } from "react-router-dom";
import NotificationBell from "./NotificationBell";
import "./Topbar.css";

const BREADCRUMB_MAP = {
  "/dashboard": ["Dashboard"],
  "/borrowers": ["Borrowers"],
  "/loan-requests": ["Lending", "Loan Requests"],
  "/loans": ["Lending", "Loans"],
  "/cases": ["Lending", "Cases"],
  "/simulations": ["Lending", "Simulations"],
  "/financial-intelligence": ["Financial Intelligence", "Overview"],
  "/financial-intelligence/news": ["Financial Intelligence", "Live News"],
  "/financial-intelligence/markets": ["Financial Intelligence", "Markets"],
  "/financial-intelligence/economy": ["Financial Intelligence", "Economy"],
  "/financial-intelligence/credit": ["Financial Intelligence", "Credit Environment"],
  "/financial-intelligence/watchlist": ["Financial Intelligence", "Watchlist"],
  "/financial-intelligence/sources": ["Financial Intelligence", "Sources"],
  "/security": ["Governance", "Security Center"],
  "/financial-intelligence/alerts": ["Financial Intelligence", "Alerts"],
  "/admin/overview": ["Governance", "Admin Overview"],
  "/admin/approvals": ["Governance", "Approvals"],
  "/admin/model": ["Governance", "Model Performance"],
  "/admin/policies": ["Governance", "Risk Policies"],
  "/admin/settings": ["System", "Settings"],
};

export default function Topbar({ searchQuery, onSearchChange }) {
  const location = useLocation();
  const navigate = useNavigate();

  const getBreadcrumb = () => {
    const path = location.pathname;
    if (path.startsWith("/borrower/")) return ["Borrowers", "Borrower Details"];
    if (path.startsWith("/loan-requests/")) return ["Lending", "Loan Request"];
    if (path.startsWith("/loans/")) return ["Lending", "Loan Details"];
    if (path.startsWith("/financial-intelligence/news/")) return ["Financial Intelligence", "Article"];
    if (path.startsWith("/financial-intelligence/markets/")) return ["Financial Intelligence", "Asset Details"];
    return BREADCRUMB_MAP[path] || ["Dashboard"];
  };

  const handleSearch = (v) => {
    onSearchChange?.(v);
    if (location.pathname !== "/borrowers") navigate("/borrowers");
  };

  const crumbs = getBreadcrumb();

  return (
    <header className="topbar">
      <div className="topbar-left">
        <nav className="topbar-breadcrumb">
          {crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="topbar-sep">/</span>}
              <span className={i === crumbs.length - 1 ? "topbar-crumb-active" : "topbar-crumb"}>{c}</span>
            </span>
          ))}
        </nav>
      </div>
      <div className="topbar-right">
        <NotificationBell />
        <div className="topbar-search">
          <svg className="topbar-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
          </svg>
          <input
            type="text"
            placeholder="Search borrowers, IDs…"
            aria-label="Search borrowers and IDs"
            value={searchQuery || ""}
            onChange={(e) => handleSearch(e.target.value)}
            className="topbar-search-input"
          />
        </div>
      </div>
    </header>
  );
}
