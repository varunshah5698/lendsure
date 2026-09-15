import { useState, useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth, isGuest } from "./context/AuthContext";
import { ToastProvider } from "./components/ui/Toast";
import Sidebar from "./components/layout/Sidebar";
import Topbar from "./components/layout/Topbar";
import CommandPalette from "./components/layout/CommandPalette";
import ScrollTop from "./components/ui/ScrollTop";
import ErrorBoundary from "./components/ui/ErrorBoundary";
import Landing from "./pages/Landing";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Borrowers from "./pages/Borrowers";
import BorrowerDetails from "./pages/BorrowerDetails";
import LoanRequests from "./pages/LoanRequests";
import LoanRequestDetail from "./pages/LoanRequestDetail";
import Loans from "./pages/Loans";
import LoanDetail from "./pages/LoanDetail";
import Cases from "./pages/Cases";
import Assistant from "./pages/Assistant";
import Simulations from "./pages/Simulations";
import Officers from "./pages/Officers";
import Grievance from "./pages/Grievance";
import GrievanceTrack from "./pages/GrievanceTrack";
import Grievances from "./pages/Grievances";
import GrievanceDetail from "./pages/GrievanceDetail";
import Security from "./pages/Security";
import AdminModel from "./pages/AdminModel";
import AdminOverview from "./pages/AdminOverview";
import AdminApprovals from "./pages/AdminApprovals";
import AdminPolicies from "./pages/AdminPolicies";
import AdminSettings from "./pages/AdminSettings";
import AdminJobs from "./pages/AdminJobs";
import "./App.css";

function RequireAuth({ children }) {
  const { session, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="loading-screen"><div className="loading-spinner" /></div>;
  if (!session) {
    // Remember where they were headed so /auth can say sign-in is required.
    try { sessionStorage.setItem("ls_login_required", location.pathname); } catch {}
    return <Navigate to="/auth" replace />;
  }
  return children;
}

// Lender-only pages: guests are bounced back to the dashboard.
// (The backend enforces the same boundary with 403s — this just hides it.)
function RequireLender({ children }) {
  const { session } = useAuth();
  if (isGuest(session)) return <Navigate to="/dashboard" replace />;
  return children;
}

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState("");
  const location = useLocation();

  const prevPath = useRef(location.pathname);

  useEffect(() => {
    // Only clear the global search when leaving the Borrowers page,
    // so Topbar searches that navigate *to* /borrowers keep their query.
    if (prevPath.current === "/borrowers" && location.pathname !== "/borrowers") {
      setSearch("");
    }
    prevPath.current = location.pathname;
  }, [location.pathname]);

  return (
    <div className="app-layout">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div className={`app-main ${collapsed ? "app-main-collapsed" : ""}`}>
        <Topbar searchQuery={search} onSearchChange={setSearch} />
        <div className="app-content">
          <ErrorBoundary>
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/borrowers" element={<Borrowers searchQuery={search} />} />
            <Route path="/borrower/:id" element={<BorrowerDetails />} />
            <Route path="/loan-requests" element={<RequireLender><LoanRequests /></RequireLender>} />
            <Route path="/loan-requests/:id" element={<RequireLender><LoanRequestDetail /></RequireLender>} />
            <Route path="/loans" element={<RequireLender><Loans /></RequireLender>} />
            <Route path="/loans/:id" element={<RequireLender><LoanDetail /></RequireLender>} />
            <Route path="/cases" element={<RequireLender><Cases /></RequireLender>} />
            <Route path="/grievances" element={<RequireLender><Grievances /></RequireLender>} />
            <Route path="/grievances/:id" element={<RequireLender><GrievanceDetail /></RequireLender>} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/simulations" element={<RequireLender><Simulations /></RequireLender>} />
            <Route path="/security" element={<RequireLender><Security /></RequireLender>} />
            <Route path="/admin/overview" element={<RequireLender><AdminOverview /></RequireLender>} />
            <Route path="/admin/officers" element={<RequireLender><Officers /></RequireLender>} />
            <Route path="/admin/approvals" element={<RequireLender><AdminApprovals /></RequireLender>} />
            <Route path="/admin/model" element={<RequireLender><AdminModel /></RequireLender>} />
            <Route path="/admin/policies" element={<RequireLender><AdminPolicies /></RequireLender>} />
            <Route path="/admin/settings" element={<RequireLender><AdminSettings /></RequireLender>} />
            <Route path="/admin/jobs" element={<RequireLender><AdminJobs /></RequireLender>} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
          </ErrorBoundary>
        </div>
        <ScrollTop />
        <CommandPalette />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/auth" element={<Auth />} />
            <Route path="/grievance" element={<Grievance />} />
            <Route path="/grievance/track" element={<GrievanceTrack />} />
            <Route path="/*" element={<RequireAuth><AppLayout /></RequireAuth>} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
