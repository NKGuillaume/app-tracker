import type { ApplicationStatus } from "../api/client";
import { api } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";

/* Official multicolor Google "G" mark, required branding for the sign-in
   button. Not a hand-rolled icon. */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

/* Example rows rendered with the real StatusBadge component, so the preview
   is the actual UI rather than a mock screenshot. Data is illustrative. */
const EXAMPLE_ROWS: { company: string; title: string; status: ApplicationStatus }[] = [
  { company: "Larkspur Health", title: "Software Engineer Intern", status: "interview" },
  { company: "Tidewater Systems", title: "Backend Engineer", status: "applied" },
  { company: "Fernhill Labs", title: "Data Engineering Intern", status: "offer" },
  { company: "Halcyon Bio", title: "Platform Engineer", status: "rejected" },
];

export function Login() {
  return (
    <main className="login">
      <section className="login__copy">
        <h1>Every application, tracked from your inbox.</h1>
        <p>
          Connect Gmail once. Confirmations, interviews, offers and rejections sort themselves
          into one list.
        </p>
        {/* Full-page navigation, not a fetch: OAuth requires a top-level redirect. */}
        <a href={api.loginUrl()} className="btn btn--ghost btn--lg">
          <GoogleMark />
          Sign in with Google
        </a>
        <p className="login__fineprint">Read-only Gmail access. Edit or delete any entry.</p>
      </section>

      <section className="login__preview" aria-label="Example of the tracker">
        <ul className="preview-list">
          {EXAMPLE_ROWS.map((row) => (
            <li key={row.company}>
              <div>
                <span className="preview-list__company">{row.company}</span>
                <span className="preview-list__title">{row.title}</span>
              </div>
              <StatusBadge status={row.status} />
            </li>
          ))}
        </ul>
        <p className="login__caption">Example data</p>
      </section>
    </main>
  );
}
