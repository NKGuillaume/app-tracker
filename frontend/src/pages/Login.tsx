import { api } from "../api/client";

export function Login() {
  return (
    <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <h1>Application Tracker</h1>
        <p>Sign in with Google to start tracking your job applications.</p>
        {/* Full-page navigation, not a fetch — OAuth requires a top-level redirect. */}
        <a href={api.loginUrl()}>
          <button type="button">Sign in with Google</button>
        </a>
      </div>
    </div>
  );
}
