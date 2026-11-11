import { NavLink } from "react-router-dom";
import type { User } from "../api/client";
import { api } from "../api/client";

interface AppHeaderProps {
  user: User;
  onLoggedOut: () => void;
}

export function AppHeader({ user, onLoggedOut }: AppHeaderProps) {
  const handleLogout = async () => {
    await api.logout().catch(() => undefined);
    onLoggedOut();
  };

  return (
    <header className="app-header">
      <div className="app-header__left">
        <h1>Application Tracker</h1>
        <nav className="app-nav" aria-label="Main">
          <NavLink to="/" end className="app-nav__link">
            Applications
          </NavLink>
          <NavLink to="/interviews" className="app-nav__link">
            Interviews
          </NavLink>
        </nav>
      </div>
      <div className="app-header__user">
        <span className="app-header__name">{user.name ?? user.email}</span>
        <button type="button" className="btn btn--ghost" onClick={handleLogout}>
          Log out
        </button>
      </div>
    </header>
  );
}
