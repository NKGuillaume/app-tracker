import { Navigate, Route, Routes } from "react-router-dom";
import { useCurrentUser } from "./api/useCurrentUser";
import { AuthCallback } from "./pages/AuthCallback";
import { Dashboard } from "./pages/Dashboard";
import { Interviews } from "./pages/Interviews";
import { Login } from "./pages/Login";

function Root() {
  const { user, loading, unreachable, refetch } = useCurrentUser();

  if (loading) {
    return (
      <div className="center-screen">
        <p className="status-text">Loading...</p>
      </div>
    );
  }

  if (unreachable) {
    return (
      <div className="center-screen">
        <div className="notice" role="alert">
          <h1>Can&apos;t reach the server</h1>
          <p>The backend didn&apos;t respond. Check that it&apos;s running, then try again.</p>
          <button type="button" className="btn btn--primary" onClick={refetch}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  // Signed-in routes live under Root so the session is checked once, not on
  // every page change.
  return (
    <Routes>
      <Route path="/" element={<Dashboard user={user} onLoggedOut={refetch} />} />
      <Route path="/interviews" element={<Interviews user={user} onLoggedOut={refetch} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="*" element={<Root />} />
    </Routes>
  );
}
