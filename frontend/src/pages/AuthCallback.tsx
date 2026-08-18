import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    // The backend has already set the session cookie by the time it redirects here;
    // this just confirms the session is valid before entering the app.
    api
      .me()
      .then(() => navigate("/", { replace: true }))
      .catch(() => navigate("/", { replace: true }));
  }, [navigate]);

  return (
    <div className="center-screen">
      <p className="status-text">Signing you in...</p>
    </div>
  );
}
