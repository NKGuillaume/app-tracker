import { useState } from "react";
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

  const gmailThreadUrl = `https://mail.google.com/mail/u/0/#inbox/${application.gmail_thread_id}`;

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
    await api.deleteApplication(application.id);
    onDeleted();
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        height: "100vh",
        width: "380px",
        backgroundColor: "white",
        boxShadow: "-2px 0 12px rgba(0,0,0,0.15)",
        padding: "1.5rem",
        overflowY: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Edit Application</h2>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>

      <label style={{ display: "block", marginTop: "1rem" }}>
        Company
        <input
          type="text"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          style={{ width: "100%", marginTop: "0.25rem" }}
        />
      </label>

      <label style={{ display: "block", marginTop: "1rem" }}>
        Job Title
        <input
          type="text"
          value={jobTitle}
          onChange={(e) => setJobTitle(e.target.value)}
          style={{ width: "100%", marginTop: "0.25rem" }}
        />
      </label>

      <label style={{ display: "block", marginTop: "1rem" }}>
        Status
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as ApplicationStatus)}
          style={{ width: "100%", marginTop: "0.25rem" }}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      {application.raw_snippet && (
        <div style={{ marginTop: "1rem" }}>
          <strong>Email snippet</strong>
          <p style={{ color: "#666", fontSize: "0.9rem" }}>{application.raw_snippet}</p>
        </div>
      )}

      <a href={gmailThreadUrl} target="_blank" rel="noreferrer" style={{ display: "block", marginTop: "1rem" }}>
        View email thread in Gmail
      </a>

      <div style={{ display: "flex", gap: "0.75rem", marginTop: "1.5rem" }}>
        <button type="button" onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </button>
        <button type="button" onClick={handleDelete} style={{ color: "#d1453b" }}>
          Delete
        </button>
      </div>
    </div>
  );
}
