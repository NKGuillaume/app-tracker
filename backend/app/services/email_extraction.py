from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings
from app.models.extraction import EmailExtraction

MODEL = "gpt-4.1-mini"

# Static and reused on every call. Does double duty as both the classification and
# extraction spec, in one round trip, so the heuristic pre-filter doesn't need a
# second pass.
EXTRACTION_SYSTEM_PROMPT = """\
You are classifying and extracting structured data from a single email that a job
seeker received. Determine whether the email is genuinely about a job application
they submitted, and if so, extract the company, job title, application date, and
status.

Set is_job_application_email to false (with all other fields null/"unknown") for:
- Job alert digests, "new jobs matching your search" emails
- Newsletters, marketing, or promotional content
- Recruiter cold outreach where the recipient has not already applied to a role

An automated or auto-responder sender address (noreply@, careerautoresponder@,
talent@, do-not-reply@) does NOT make an email promotional. Application receipts
and status updates are almost always sent from such addresses -- classify by what
the email says about their application, not by the sender's automation.

Worked examples:
- Subject "Your application to Acme Corp was received" from Greenhouse
  -> is_job_application_email=true, status="applied"
- "We've received your application!" from an automated talent-acquisition address
  -> is_job_application_email=true, status="applied"
- "Complete Your Technical Assessment" or an online-assessment / HireVue / coding
  test invitation for a role they applied to
  -> is_job_application_email=true, status="interview"
- "We'd like to schedule a call to discuss your background"
  -> is_job_application_email=true, status="interview"
- "After careful consideration, we've decided to move forward with other candidates"
  -> is_job_application_email=true, status="rejected"
- "We're excited to offer you the Software Engineer position"
  -> is_job_application_email=true, status="offer"
- "5 new Software Engineer jobs matching your search"
  -> is_job_application_email=false

Infer application_date from the email's own content when it mentions a date;
otherwise leave it null (the caller falls back to the email's send date).
Set confidence to reflect how certain you are given the available text.

When status is "interview", also fill the interview fields (leave them null
otherwise):
- interview_type:
  - "online_assessment": timed coding or skills test (HackerRank, CodeSignal,
    Codility, CoderPad take-home, Karat async, aptitude tests)
  - "video_interview": recorded one-way video (HireVue, Spark Hire, Willo)
  - "phone_screen": recruiter or HR call
  - "technical_interview": live coding, system design, or technical deep-dive
    with an engineer
  - "behavioral_interview": hiring manager, culture-fit, or behavioral round
  - "final_round": onsite, superday, or a final multi-round loop
  - "other": an interview step that fits none of these
- assessment_platform: the platform the email names, or null. Never guess one.
- interview_deadline: the due date or scheduled date the email states. Resolve
  relative phrases ("within 7 days") from the email's sent date. Null if none.
- team: the team or group if the email names one ("Payments team"), else null.
"""


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def classify_and_extract(
    subject: str, sender: str, body_text: str, sent_date: str | None = None
) -> EmailExtraction:
    # The sent date lets the model resolve "complete within 7 days" into a deadline.
    sent_line = f"Sent: {sent_date}\n" if sent_date else ""
    user_content = f"Subject: {subject}\nFrom: {sender}\n{sent_line}\n{body_text}"

    completion = _client().chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format=EmailExtraction,
    )

    message = completion.choices[0].message
    if message.refusal or message.parsed is None:
        # Model declined or returned content that didn't validate against the schema --
        # treat as a non-match rather than raising, so one bad email can't break a
        # whole sync run.
        return EmailExtraction(is_job_application_email=False, status="unknown", confidence=0.0)

    return message.parsed


MATCH_SYSTEM_PROMPT = """\
A job seeker received a status email (interview invitation, rejection, or offer).
Decide which of their existing applications it belongs to.

Match on the hiring company and role. Company names may be abbreviated or
written differently ("OKC Thunder" = "Oklahoma City Thunder", "JPMC" =
"JPMorgan Chase"). Roles may be worded differently or include locations,
years, or requisition numbers.

Return the id of the single application it clearly belongs to. Return null if
none fits, or if several fit and you cannot tell which one. A wrong match is
worse than no match.
"""


class _ApplicationMatch(BaseModel):
    application_id: str | None


def match_application(
    company: str | None, job_title: str | None, status: str, candidates: list[dict]
) -> str | None:
    """AI fallback for status emails the deterministic rules couldn't place.
    Returns a candidate id, or None. Callers must validate the id."""
    listing = "\n".join(
        f"- id={c['id']} | company={c.get('company')} | role={c.get('job_title') or 'unknown'}"
        for c in candidates
    )
    completion = _client().chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Email: {status} for company={company} | role={job_title or 'not stated'}\n\n"
                    f"Existing applications:\n{listing}"
                ),
            },
        ],
        response_format=_ApplicationMatch,
    )
    message = completion.choices[0].message
    if message.refusal or message.parsed is None:
        return None
    return message.parsed.application_id
