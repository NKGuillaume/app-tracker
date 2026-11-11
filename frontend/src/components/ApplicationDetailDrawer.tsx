import { type FormEvent, useEffect, useRef, useState } from "react";
import type { Application, ApplicationStatus, InterviewType } from "../api/client";
import { api } from "../api/client";
import { capitalize } from "../format";
import { INTERVIEW_TYPE_LABELS, INTERVIEW_TYPES } from "../interviewTypes";

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
  const [interviewType, setInterviewType] = useState<InterviewType | "">(
    application.interview_type ?? "",
  );
  const [platform, setPlatform] = useState(application.assessment_platform ?? "");
  const [deadline, setDeadline] = useState(application.interview_deadline ?? "");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  const gmailThreadUrl = `https://mail.google.com/mail/u/0/#all/${application.gmail_thread_id}`;
  const companyMissing = company.trim() === "";

  // Move focus into the dialog, return it to where it was on close, and
  // stop the page behind from scrolling.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    firstFieldRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    if (companyMissing) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateApplication(application.id, {
        company: company.trim(),
        job_title: jobTitle.trim() || null,
        status,
        ...(status === "interview" && {
          interview_type: interviewType || null,
          assessment_platform: platform.trim() || null,
          interview_deadline: deadline || null,
        }),
      });
      onSaved();
    } catch {
      setError("Couldn't save changes. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await api.deleteApplication(application.id);
      onDeleted();
    } catch {
      setError("Couldn't delete this application. Try again.");
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <form
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onSubmit={handleSave}
      >
        <div className="drawer__header">
          <h2 id="drawer-title">Edit application</h2>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <label className="field">
          <span>Company</span>
          <input
            ref={firstFieldRef}
            type="text"
            className="input"
            value={company}
            required
            aria-invalid={companyMissing}
            aria-describedby={companyMissing ? "company-error" : undefined}
            onChange={(e) => setCompany(e.target.value)}
          />
          {companyMissing && (
            <small id="company-error" className="field__error">
              Company is required.
            </small>
          )}
        </label>

        <label className="field">
          <span>Job title</span>
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
                {capitalize(option)}
              </option>
            ))}
          </select>
        </label>

        {status === "interview" && (
          <>
            <label className="field">
              <span>Interview type</span>
              <select
                className="select"
                value={interviewType}
                onChange={(e) => setInterviewType(e.target.value as InterviewType | "")}
              >
                <option value="">Not set</option>
                {INTERVIEW_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {INTERVIEW_TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Platform</span>
              <input
                type="text"
                className="input"
                value={platform}
                aria-describedby="platform-help"
                onChange={(e) => setPlatform(e.target.value)}
              />
              <small id="platform-help" className="field__help">
                For example HackerRank, CodeSignal or HireVue
              </small>
            </label>

            <label className="field">
              <span>Due or scheduled date</span>
              <input
                type="date"
                className="input"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
              />
            </label>
          </>
        )}

        {application.raw_snippet && (
          <div className="drawer__snippet">
            <strong>Email snippet</strong>
            <p>{application.raw_snippet}</p>
          </div>
        )}

        <a href={gmailThreadUrl} target="_blank" rel="noreferrer" className="drawer__link">
          Open email thread in Gmail
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <div className="drawer__actions">
          <button
            type="submit"
            className="btn btn--primary"
            disabled={saving || deleting || companyMissing}
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            type="button"
            className={`btn ${confirmingDelete ? "btn--danger-confirm" : "btn--danger"}`}
            onClick={handleDelete}
            onBlur={() => setConfirmingDelete(false)}
            disabled={saving || deleting}
          >
            {deleting ? "Deleting..." : confirmingDelete ? "Confirm delete" : "Delete"}
          </button>
        </div>
      </form>
    </>
  );
}
