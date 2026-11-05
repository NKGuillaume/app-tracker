import { useEffect, useState } from "react";
import type { SyncResult } from "../api/client";
import { api } from "../api/client";

interface SyncButtonProps {
  onSyncComplete: () => void;
}

function summarize(result: SyncResult): string {
  const parts: string[] = [];
  if (result.new_applications) parts.push(`${result.new_applications} new`);
  if (result.updated_applications) parts.push(`${result.updated_applications} updated`);
  return parts.length ? `Sync done: ${parts.join(", ")}` : "Sync done: nothing new";
}

export function SyncButton({ onSyncComplete }: SyncButtonProps) {
  const [syncing, setSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
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
    setResult(null);
    try {
      const syncResult = await api.syncManual();
      setResult(summarize(syncResult));
      const status = await api.syncStatus().catch(() => null);
      if (status) setLastSyncedAt(status.last_manual_sync_at);
      onSyncComplete();
    } catch {
      setError("Sync failed. Try again in a moment.");
    } finally {
      setSyncing(false);
    }
  };

  let note: JSX.Element | null = null;
  if (error) {
    note = <span className="sync-error">{error}</span>;
  } else if (syncing) {
    note = <span className="sync-note">Scanning Gmail, this can take a minute</span>;
  } else if (result) {
    note = <span className="sync-note">{result}</span>;
  } else if (lastSyncedAt) {
    note = (
      <span className="sync-note">Last synced {new Date(lastSyncedAt).toLocaleString()}</span>
    );
  }

  return (
    <div className="sync">
      <span role="status" aria-live="polite">
        {note}
      </span>
      <button type="button" className="btn btn--primary" onClick={handleSync} disabled={syncing}>
        {syncing ? "Syncing..." : "Sync now"}
      </button>
    </div>
  );
}
