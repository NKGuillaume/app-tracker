"""Tailored interview prep tips for one application, grounded in its email.

One structured OpenAI call per application, cached on the row by the caller.
The same call also classifies the interview (type / platform / deadline), so
older rows that predate interview extraction get filled in when first opened.
"""

from datetime import date

from pydantic import BaseModel

from app.models.extraction import InterviewType
from app.services.email_extraction import MODEL, _client

PREP_SYSTEM_PROMPT = """\
You help a job seeker prepare for one specific interview step. You get the
company, role, what is already known about the step, and the invitation email.

Ground everything in the email first: duration, number of questions, allowed
languages, proctoring, format, deadline, who they will meet. Use general,
well-known knowledge of the named platform's format (for example: HackerRank
and CodeSignal run hidden test cases and let you pick a language; HireVue gives
limited thinking time per recorded answer). Do NOT invent company-specific
facts (interview questions, team culture, salary, number of rounds) that the
email does not state. Never include URLs.

Write for a student or early-career candidate. Be concrete and actionable:
"Practice 2 medium array/string problems a day in a 90-minute timed block",
not "practice coding".

Fields:
- interview_type / assessment_platform / interview_deadline: classify the step
  from the email. Platform and deadline only if the email states them. Resolve
  relative deadlines from the email's sent date.
- what_to_expect: 2-3 sentences on the format, citing specifics from the email.
- prep_steps: 4-6 steps in the order to do them, each a short title plus a 1-2
  sentence detail.
- practice_topics: 3-6 short topic names to practice for this step.
- day_of_tips: 3-5 short tips for the day itself (setup, timing, environment).
"""


class PrepStep(BaseModel):
    title: str
    detail: str


class InterviewPrep(BaseModel):
    interview_type: InterviewType
    assessment_platform: str | None = None
    interview_deadline: date | None = None
    what_to_expect: str
    prep_steps: list[PrepStep]
    practice_topics: list[str]
    day_of_tips: list[str]


def generate_interview_prep(application: dict, email: dict | None) -> InterviewPrep:
    """`email` is the summary from gmail_client (None if it couldn't be fetched;
    the tips then rest on the stored snippet alone)."""
    known = [
        f"Company: {application.get('company') or 'unknown'}",
        f"Role: {application.get('job_title') or 'unknown'}",
    ]
    for label, key in [
        ("Team", "team"),
        ("Interview type so far", "interview_type"),
        ("Platform", "assessment_platform"),
        ("Deadline", "interview_deadline"),
    ]:
        if application.get(key):
            known.append(f"{label}: {application[key]}")

    if email:
        email_text = (
            f"Subject: {email['subject']}\nFrom: {email['sender']}\n"
            f"Sent: {email.get('sent_date') or 'unknown'}\n\n{email['body_text']}"
        )
    else:
        email_text = f"(Full email unavailable. Snippet: {application.get('raw_snippet') or 'none'})"

    completion = _client().chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": PREP_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(known) + "\n\nInvitation email:\n" + email_text},
        ],
        response_format=InterviewPrep,
    )
    message = completion.choices[0].message
    if message.refusal or message.parsed is None:
        raise RuntimeError("The model did not return prep tips")
    return message.parsed
