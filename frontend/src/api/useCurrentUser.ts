import { useEffect, useState } from "react";
import { ApiError, api, type User } from "./client";

interface CurrentUserState {
  user: User | null;
  loading: boolean;
  /* True when the backend could not be reached or answered with a non-auth
     error. Distinct from "not signed in" so the UI doesn't show the login
     screen for an outage. */
  unreachable: boolean;
  refetch: () => void;
}

export function useCurrentUser(): CurrentUserState {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setUnreachable(false);

    api
      .me()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch((err) => {
        if (cancelled) return;
        setUser(null);
        if (!(err instanceof ApiError && err.status === 401)) {
          setUnreachable(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [version]);

  return { user, loading, unreachable, refetch: () => setVersion((v) => v + 1) };
}
