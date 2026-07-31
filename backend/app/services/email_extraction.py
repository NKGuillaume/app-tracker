from functools import lru_cache

from openai import OpenAI

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

Worked examples:
- Subject "Your application to Acme Corp was received" from Greenhouse
  -> is_job_application_email=true, status="applied"
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
"""


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def classify_and_extract(subject: str, sender: str, body_text: str) -> EmailExtraction:
    user_content = f"Subject: {subject}\nFrom: {sender}\n\n{body_text}"

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
