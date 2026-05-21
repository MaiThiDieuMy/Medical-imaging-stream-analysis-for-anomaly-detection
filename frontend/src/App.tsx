import { useEffect, useMemo, useState } from "react";
import { clearAccessToken, getAccessToken, getMe, logout } from "./api/client";
import { AdminModelsPage } from "./pages/AdminModelsPage";
import { AnalyzePage } from "./pages/AnalyzePage";
import { CasesPage } from "./pages/CasesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { ReviewMlopsPage } from "./pages/ReviewMlopsPage";
import { UserManagementPage } from "./pages/UserManagementPage";
import type { UserPublic } from "./types/api";
import {
  defaultPageForRole,
  getNavigationForRole,
  type PageKey,
  roleLabel,
} from "./utils/navigation";

function App() {
  const [currentUser, setCurrentUser] = useState<UserPublic | null>(null);
  const [page, setPage] = useState<PageKey>("dashboard");
  const [authLoading, setAuthLoading] = useState(Boolean(getAccessToken()));

  useEffect(() => {
    if (!getAccessToken()) {
      return;
    }
    getMe()
      .then((user) => {
        setCurrentUser(user);
        setPage(defaultPageForRole(user.role));
      })
      .catch(() => {
        clearAccessToken();
      })
      .finally(() => setAuthLoading(false));
  }, []);

  const navItems = useMemo(
    () => (currentUser ? getNavigationForRole(currentUser.role) : []),
    [currentUser],
  );

  function handleLogin(user: UserPublic) {
    setCurrentUser(user);
    setPage(defaultPageForRole(user.role));
  }

  async function handleLogout() {
    await logout();
    setCurrentUser(null);
    setPage("dashboard");
  }

  if (authLoading) {
    return (
      <main className="login-screen">
        <div className="login-panel">
          <p className="muted">Đang kiểm tra phiên đăng nhập...</p>
        </div>
      </main>
    );
  }

  if (!currentUser) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">XR</div>
          <div>
            <h1>Medical Imaging Stream Analysis</h1>
            <span>Hệ thống phân tích ảnh X-quang lồng ngực</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="Main navigation">
          {navItems.map((item) => (
            <button
              className={page === item.key ? "active" : ""}
              key={item.key}
              onClick={() => setPage(item.key)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-user">
          <span>{roleLabel(currentUser.role)}</span>
          <strong>{currentUser.full_name}</strong>
          <small>{currentUser.username}</small>
          <button onClick={() => void handleLogout()} type="button">
            Đăng xuất
          </button>
        </div>
      </aside>
      <main className="content">
        {page === "dashboard" && (
          <DashboardPage currentUser={currentUser} onNavigate={setPage} />
        )}
        {page === "analyze" && <AnalyzePage onOpenCases={() => setPage("cases")} />}
        {page === "cases" && <CasesPage role={currentUser.role} />}
        {page === "models" && <AdminModelsPage />}
        {page === "reviews" && (
          <ReviewMlopsPage isAdmin={currentUser.role === "admin"} />
        )}
        {page === "users" && <UserManagementPage />}
        {page === "monitoring" && <MonitoringPage />}
      </main>
    </div>
  );
}

export default App;
