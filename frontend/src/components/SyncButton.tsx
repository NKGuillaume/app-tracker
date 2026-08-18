import { useEffect, useState } from "react";
import { api } from "../api/client";

interface SyncButtonProps {
  onSyncComplete: () => void;
}

export function SyncButton({ onSyncComplete }: SyncButtonProps) {
  const [syncing, setSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .syncStatus()
      .then((s) => setLastSyncedAt(s.last_manual_sync_at))
      .catch(() => undefined);
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      await api.syncManual();
      const status = await api.syncStatus();
      setLastSyncedAt(status.last_manual_sync_at);
      onSyncComplete();
    } catch {
      setError("Sync failed. Try again in a moment.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
      {error && <span className="sync-error">{error}</span>}
      {!error && lastSyncedAt && (
        <span className="sync-note">Last synced {new Date(lastSyncedAt).toLocaleString()}</span>
      )}
      <button type="button" className="btn btn--primary" onClick={handleSync} disabled={syncing}>
        {syncing ? "Syncing..." : "Sync now"}
      </button>
    </div>
  );
}
