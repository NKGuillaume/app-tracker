import { Route, Routes } from "react-router-dom";
import { useCurrentUser } from "./api/useCurrentUser";
import { AuthCallback } from "./pages/AuthCallback";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";

function Root() {
  const { user, loading, refetch } = useCurrentUser();

  if (loading) {
    return (
      <div className="center-screen">
        <p className="status-text">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  return <Dashboard user={user} onLoggedOut={refetch} />;
}

export function App() {
  return (
    <Routes>
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/" element={<Root />} />
    </Routes>
  );
}
