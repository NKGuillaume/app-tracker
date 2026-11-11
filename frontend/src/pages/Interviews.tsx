import { useCallback, useEffect, useMemo, useState } from "react";
import type { Application, InterviewType, User } from "../api/client";
import { ApiError, api } from "../api/client";
import { AppHeader } from "../components/AppHeader";
import { ApplicationDetailDrawer } from "../components/ApplicationDetailDrawer";
import { formatDate, parseDate } from "../format";

/* Section order follows a typical hiring funnel. Rows with no type yet (synced
   before interview extraction) land in the last section and get classified
   when their prep tips are generated. */
const SECTIONS: { type: InterviewType | null; title: string }[] = [
  { type: "online_assessment", title: "Online assessments" },
  { type: "video_interview", title: "Recorded video interviews" },
  { type: "phone_screen", title: "Phone screens" },
  { type: "technical_interview", title: "Technical interviews" },
  { type: "behavioral_interview", title: "Behavioral interviews" },
  { type: "final_round", title: "Final rounds" },
  { type: null, title: "Other" },
];

function sectionOf(app: Application): InterviewType | null {
  return app.interview_type && app.interview_type !== "other" ? app.interview_type : null;
}

function relativeDay(value: string): { text: string; past: boolean } {
  const target = parseDate(value);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (days === 0) return { text: "Today", past: false };
  if (days === 1) return { text: "Tomorrow", past: false };
  if (days > 1) return { text: `In ${days} days`, past: false };
  if (days === -1) return { text: "Yesterday", past: true };
  return { text: `${-days} days ago`, past: true };
}

/* What needs attention first: upcoming deadlines (soonest first), then undated
   items (most recently updated first), then deadlines that have passed (most
   recent first), which are usually already done. */
function compareInterviews(a: Application, b: Application): number {
  const rank = (app: Application) => {
    if (!app.interview_deadline) return 1;
    return relativeDay(app.interview_deadline).past ? 2 : 0;
  };
  const ra = rank(a);
  const rb = rank(b);
  if (ra !== rb) return ra - rb;
  if (ra === 0) return a.interview_deadline!.localeCompare(b.interview_deadline!);
  if (ra === 2) return b.interview_deadline!.localeCompare(a.interview_deadline!);
  return b.updated_at.localeCompare(a.updated_at);
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const detail = JSON.parse(err.message).detail;
      if (typeof detail === "string") return detail;
    } catch {
      /* not JSON; fall through */
    }
  }
  return "Couldn't generate prep tips. Try again.";
}

interface PrepState {
  loading: boolean;
  error: string | null;
}

interface InterviewsProps {
  user: User;
  onLoggedOut: () => void;
}

export function Interviews({ user, onLoggedOut }: InterviewsProps) {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // Expansion and prep progress live here, keyed by id, so a card keeps its
  // state if generating tips classifies it and it moves to another section.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [prep, setPrep] = useState<Record<string, PrepState>>({});
  const [editing, setEditing] = useState<Application | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api
      .listApplications({ status: "interview", page: 1, page_size: 100 })
      .then((result) => setApps(result.items))
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const sections = useMemo(
    () =>
      SECTIONS.map((section) => ({
        ...section,
        items: apps.filter((a) => sectionOf(a) === section.type).sort(compareInterviews),
      })).filter((section) => section.items.length > 0),
    [apps],
  );

  const generate = async (app: Application, regenerate: boolean) => {
    setPrep((p) => ({ ...p, [app.id]: { loading: true, error: null } }));
    try {
      const updated = await api.interviewPrep(app.id, regenerate);
      setApps((list) => list.map((a) => (a.id === updated.id ? updated : a)));
      setPrep((p) => ({ ...p, [app.id]: { loading: false, error: null } }));
    } catch (err) {
      setPrep((p) => ({ ...p, [app.id]: { loading: false, error: errorText(err) } }));
    }
  };

  const toggle = (app: Application) => {
    const opening = !expanded.has(app.id);
    setExpanded((set) => {
      const next = new Set(set);
      if (opening) next.add(app.id);
      else next.delete(app.id);
      return next;
    });
    if (opening && !app.interview_prep && !prep[app.id]?.loading) {
      void generate(app, false);
    }
  };

  let body: JSX.Element;
  if (loadError) {
    body = (
      <div className="table-card">
        <div className="empty-state" role="alert">
          <h2>Couldn&apos;t load interviews</h2>
          <p>Something went wrong talking to the server.</p>
          <button type="button" className="btn btn--ghost" onClick={load}>
            Try again
          </button>
        </div>
      </div>
    );
  } else if (loading && apps.length === 0) {
    body = (
      <div className="interview-list" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="interview-card">
            <span className="skeleton" style={{ width: "40%" }} />
            <span className="skeleton" style={{ width: "60%", marginTop: "0.6rem" }} />
          </div>
        ))}
      </div>
    );
  } else if (apps.length === 0) {
    body = (
      <div className="table-card">
        <div className="empty-state">
          <h2>No interviews yet</h2>
          <p>When an email invites you to an assessment or interview, it shows up here.</p>
        </div>
      </div>
    );
  } else {
    body = (
      <>
        {sections.map((section) => (
          <section key={section.title} className="interview-section">
            <h2>
              {section.title}
              <span className="interview-section__count">{section.items.length}</span>
            </h2>
            <ul className="interview-list">
              {section.items.map((app) => (
                <InterviewCard
                  key={app.id}
                  app={app}
                  open={expanded.has(app.id)}
                  state={prep[app.id]}
                  onToggle={() => toggle(app)}
                  onRegenerate={() => generate(app, true)}
                  onEdit={() => setEditing(app)}
                />
              ))}
            </ul>
          </section>
        ))}
      </>
    );
  }

  return (
    <div className="page">
      <AppHeader user={user} onLoggedOut={onLoggedOut} />
      <div className="page-intro">
        <h2>Interviews</h2>
        <p>Grouped by interview type, with prep tips drawn from each invitation email.</p>
      </div>
      {body}
      {editing && (
        <ApplicationDetailDrawer
          application={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
          onDeleted={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

interface InterviewCardProps {
  app: Application;
  open: boolean;
  state: PrepState | undefined;
  onToggle: () => void;
  onRegenerate: () => void;
  onEdit: () => void;
}

function InterviewCard({ app, open, state, onToggle, onRegenerate, onEdit }: InterviewCardProps) {
  const deadline = app.interview_deadline ? relativeDay(app.interview_deadline) : null;
  const panelId = `prep-${app.id}`;
  const gmailUrl = `https://mail.google.com/mail/u/0/#all/${app.gmail_thread_id}`;

  return (
    <li className="interview-card">
      <div className="interview-card__head">
        <div className="interview-card__title">
          <span className="interview-card__company">{app.company}</span>
          {app.assessment_platform && <span className="badge badge--platform">{app.assessment_platform}</span>}
        </div>
        {deadline && app.interview_deadline && (
          <span className={`interview-card__due${deadline.past ? " is-past" : ""}`}>
            {deadline.text}
            <span className="interview-card__date"> ({formatDate(app.interview_deadline)})</span>
          </span>
        )}
      </div>
      <p className="interview-card__role">
        {app.job_title ?? "Role not set"}
        {app.team && <span> &middot; {app.team}</span>}
      </p>

      <div className="interview-card__actions">
        <button
          type="button"
          className="btn btn--ghost"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
        >
          {open ? "Hide prep tips" : "Prep tips"}
        </button>
        <button type="button" className="btn btn--ghost" onClick={onEdit}>
          Edit
        </button>
        <a href={gmailUrl} target="_blank" rel="noreferrer" className="interview-card__link">
          Open email<span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      </div>

      {open && (
        <div id={panelId} className="prep">
          <PrepBody app={app} state={state} onRegenerate={onRegenerate} />
        </div>
      )}
    </li>
  );
}

function PrepBody({
  app,
  state,
  onRegenerate,
}: {
  app: Application;
  state: PrepState | undefined;
  onRegenerate: () => void;
}) {
  if (state?.loading) {
    return (
      <div aria-busy="true" aria-live="polite">
        <span className="visually-hidden">Generating prep tips</span>
        {[90, 75, 82, 60].map((w, i) => (
          <span key={i} className="skeleton prep__skeleton" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  }

  const tips = app.interview_prep;
  if (state?.error && !tips) {
    return (
      <div role="alert" className="prep__error">
        <p>{state.error}</p>
        <button type="button" className="btn btn--ghost" onClick={onRegenerate}>
          Try again
        </button>
      </div>
    );
  }
  if (!tips) return null;

  return (
    <>
      {state?.error && (
        <p role="alert" className="form-error">
          {state.error}
        </p>
      )}
      <h3>What to expect</h3>
      <p className="prep__expect">{tips.what_to_expect}</p>

      <h3>How to prepare</h3>
      <ol className="prep__steps">
        {tips.prep_steps.map((step) => (
          <li key={step.title}>
            <strong>{step.title}</strong>
            <span>{step.detail}</span>
          </li>
        ))}
      </ol>

      {tips.practice_topics.length > 0 && (
        <>
          <h3>Practice topics</h3>
          <ul className="prep__topics">
            {tips.practice_topics.map((topic) => (
              <li key={topic}>{topic}</li>
            ))}
          </ul>
        </>
      )}

      {tips.day_of_tips.length > 0 && (
        <>
          <h3>On the day</h3>
          <ul className="prep__dayof">
            {tips.day_of_tips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </>
      )}

      <div className="prep__footer">
        <span>
          AI-generated from the invitation email
          {app.interview_prep_generated_at &&
            ` on ${new Date(app.interview_prep_generated_at).toLocaleDateString()}`}
          . Check details against the email.
        </span>
        <button type="button" className="btn btn--ghost" onClick={onRegenerate}>
          Regenerate
        </button>
      </div>
    </>
  );
}
