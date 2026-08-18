import { useEffect, useState } from "react";
import type { Application, ApplicationStatus } from "../api/client";
import { api } from "../api/client";

const STATUS_OPTIONS: ApplicationStatus[] = [
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
  "unknown",
];

interface ApplicationDetailDrawerProps {
  application: Application;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}

export function ApplicationDetailDrawer({
  application,
  onClose,
  onSaved,
  onDeleted,
}: ApplicationDetailDrawerProps) {
  const [company, setCompany] = useState(application.company);
  const [jobTitle, setJobTitle] = useState(application.job_title ?? "");
  const [status, setStatus] = useState<ApplicationStatus>(application.status);
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const gmailThreadUrl = `https://mail.google.com/mail/u/0/#inbox/${application.gmail_thread_id}`;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateApplication(application.id, {
        company,
        job_title: jobTitle || null,
        status,
      });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    await api.deleteApplication(application.id);
    onDeleted();
  };

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <div className="drawer" role="dialog" aria-modal="true" aria-label="Edit application">
        <div className="drawer__header">
          <h2>Edit Application</h2>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <label className="field">
          <span>Company</span>
          <input
            type="text"
            className="input"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
        </label>

        <label className="field">
          <span>Job Title</span>
          <input
            type="text"
            className="input"
            value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)}
          />
        </label>

        <label className="field">
          <span>Status</span>
          <select
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value as ApplicationStatus)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        {application.raw_snippet && (
          <div className="drawer__snippet">
            <strong>Email snippet</strong>
            <p>{application.raw_snippet}</p>
          </div>
        )}

        <a href={gmailThreadUrl} target="_blank" rel="noreferrer" className="drawer__link">
          View email thread in Gmail ↗
        </a>

        <div className="drawer__actions">
          <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            type="button"
            className={`btn ${confirmingDelete ? "btn--danger-confirm" : "btn--danger"}`}
            onClick={handleDelete}
            onBlur={() => setConfirmingDelete(false)}
          >
            {confirmingDelete ? "Confirm delete" : "Delete"}
          </button>
        </div>
      </div>
    </>
  );
}
