import { NavLink, Link } from "react-router-dom";
import { useAuth, isGuest } from "../../context/AuthContext";
import Logo from "../ui/Logo";
import Icon from "../ui/Icon";
import "./Sidebar.css";

// lender: true = hidden from guest sessions (heavily restrained role).
const NAV = [
  { section: "Overview", items: [
    { label: "Dashboard", path: "/dashboard", icon: "grid" },
    { label: "Borrowers", path: "/borrowers", icon: "users" },
    { label: "AI Assistant", path: "/assistant", icon: "sparkles" },
  ]},
  { section: "Lending", items: [
    { label: "Loan Requests", path: "/loan-requests", icon: "file-text", lender: true },
    { label: "Loans", path: "/loans", icon: "cash", lender: true },
    { label: "Cases", path: "/cases", icon: "folder", lender: true },
    { label: "Grievances", path: "/grievances", icon: "shield-check", lender: true },
    { label: "Simulations", path: "/simulations", icon: "flask", lender: true },
  ]},
  { section: "Governance", lender: true, items: [
    { label: "Admin Overview", path: "/admin/overview", icon: "shield", lender: true },
    { label: "Recovery Officers", path: "/admin/officers", icon: "users", lender: true },
    { label: "Approvals", path: "/admin/approvals", icon: "check-circle", lender: true },
    { label: "Background Jobs", path: "/admin/jobs", icon: "clock", lender: true },
    { label: "Security Center", path: "/security", icon: "lock", lender: true },
    { label: "Model Performance", path: "/admin/model", icon: "cpu", lender: true },
    { label: "Risk Policies", path: "/admin/policies", icon: "sliders", lender: true },
    { label: "Settings", path: "/admin/settings", icon: "tool", lender: true },
  ]},
];

export default function Sidebar({ collapsed, onToggle }) {
  const { session, signOut } = useAuth();
  const guest = isGuest(session);
  const groups = NAV.filter((g) => !(guest && g.lender))
    .map((g) => ({ ...g, items: g.items.filter((i) => !(guest && i.lender)) }))
    .filter((g) => g.items.length);

  return (
    <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""}`}>
      <div className="sidebar-header">
        <Link to="/" className="sidebar-logo" title="Back to home page">
          <Logo size={32} />
          {!collapsed && <span className="sidebar-brand">LendSure</span>}
        </Link>
        <button className="sidebar-toggle" onClick={onToggle} aria-label="Toggle sidebar">
          {collapsed ? "→" : "←"}
        </button>
      </div>

      <nav className="sidebar-nav">
        {groups.map((group) => (
          <div key={group.section} className="sidebar-group">
            {!collapsed && <div className="sidebar-group-label">{group.section}</div>}
            {group.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `sidebar-link ${isActive ? "sidebar-link-active" : ""}`}
                title={collapsed ? item.label : undefined}
              >
                <span className="sidebar-icon"><Icon name={item.icon} size={18} /></span>
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        {session && (
          <div className="sidebar-user">
            <div className="sidebar-avatar">
              {(session.display_name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}
            </div>
            {!collapsed && (
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">{session.display_name}</div>
                <div className={`sidebar-user-role ${session.role === "guest" ? "role-guest" : ""}`}>
                  {session.role}
                </div>
              </div>
            )}
          </div>
        )}
        <button className="sidebar-link sidebar-logout" onClick={signOut} title="Sign out">
          <span className="sidebar-icon">↗</span>
          {!collapsed && <span>Sign out</span>}
        </button>
      </div>
    </aside>
  );
}
