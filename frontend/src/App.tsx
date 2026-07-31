import { Route, Routes } from "react-router-dom";
import { useCurrentUser } from "./api/useCurrentUser";
import { AuthCallback } from "./pages/AuthCallback";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";

function Root() {
  const { user, loading, refetch } = useCurrentUser();

  if (loading) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center" }}>
        <p>Loading...</p>
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
