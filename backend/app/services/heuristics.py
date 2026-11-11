"""Cheap, zero-cost pre-filter that decides which emails are worth sending to the
LLM extractor.

Leans broad -- a false positive costs one extra LLM call, while a false negative
means an application silently never appears -- but not so broad that job-alert
mail floods it. Measured on a real student inbox, the old rules ("intern" anywhere
in the subject, or any noreply@ sender) sent 298 of 300 emails to the LLM, 296 of
them job alerts and career newsletters. So:

- ATS sender domains and careers@/talent@/recruiting@ addresses always qualify.
- Otherwise the SUBJECT must carry an application signal. A noreply@ sender alone
  proves nothing: job-alert services send from noreply@ too.
- "intern"/"internship" only counts next to an application word, since every
  internship newsletter and alert says "internship".
- Job-alert phrasing ("just posted", "93% match", "jobs you might like") is
  excluded outright; those emails are recommendations, never applications.
"""

import re
from email.utils import parseaddr

ATS_SENDER_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "myworkday.com",
    "icims.com",
    "taleo.net",
    "smartrecruiters.com",
    "ashbyhq.com",
    "workable.com",
    "bamboohr.com",
    "jobvite.com",
]

# Mailboxes companies use specifically for hiring. noreply@/no-reply@ are NOT here
# on purpose: see the module docstring.
TRUSTED_SENDER_PATTERNS = [
    re.compile(r"^careers@", re.IGNORECASE),
    re.compile(r"^talent@", re.IGNORECASE),
    re.compile(r"^recruiting@", re.IGNORECASE),
]

_APPLICATION_WORDS = r"(application|applied|applying|offer|interview|candidacy|status|next steps)"

SUBJECT_KEYWORDS = [
    re.compile(r"application received", re.IGNORECASE),
    re.compile(r"thank you for applying", re.IGNORECASE),
    re.compile(r"thanks for applying", re.IGNORECASE),
    re.compile(r"\byour application\b", re.IGNORECASE),
    re.compile(r"\bapplication\b.*\b(submitted|received|complete|completed|confirmation)\b", re.IGNORECASE),
    re.compile(r"thanks? (you )?for your interest", re.IGNORECASE),
    re.compile(r"thank you for your application", re.IGNORECASE),
    re.compile(r"application status", re.IGNORECASE),
    re.compile(r"application update", re.IGNORECASE),
    re.compile(r"interview", re.IGNORECASE),
    re.compile(r"next steps", re.IGNORECASE),
    re.compile(r"we('re| are) (excited|pleased) to offer", re.IGNORECASE),
    re.compile(r"moving forward with other candidates", re.IGNORECASE),
    re.compile(r"your candidacy", re.IGNORECASE),
    re.compile(
        rf"\bintern(ship)?s?\b.*\b{_APPLICATION_WORDS}\b|\b{_APPLICATION_WORDS}\b.*\bintern(ship)?s?\b",
        re.IGNORECASE,
    ),
    re.compile(r"received your application", re.IGNORECASE),
    re.compile(r"\bassessment\b", re.IGNORECASE),
    re.compile(r"coding (challenge|test)", re.IGNORECASE),
    re.compile(r"hirevue", re.IGNORECASE),
]

# Recommendation/alert phrasing. Checked first and wins over everything else.
JOB_ALERT_PATTERNS = [
    re.compile(r"just posted", re.IGNORECASE),
    re.compile(r"\b\d{1,3}% match\b", re.IGNORECASE),
    re.compile(r"job matches", re.IGNORECASE),
    re.compile(r"jobs? you (might|may) like", re.IGNORECASE),
    re.compile(r"is hiring for", re.IGNORECASE),
    re.compile(r"curated for you", re.IGNORECASE),
    re.compile(r"\bjob alerts?\b", re.IGNORECASE),
    re.compile(r"recommended jobs", re.IGNORECASE),
    re.compile(r"sees you as a top applicant", re.IGNORECASE),
    re.compile(r"aligns with your background", re.IGNORECASE),
    re.compile(r"opportunity for you at", re.IGNORECASE),
    re.compile(r"^new .+\b(intern|internship|role|job|position)s? at ", re.IGNORECASE),
]

# Plain-text equivalents of the patterns above, used to build the server-side Gmail
# search query so manual sync only lists plausibly relevant messages instead of the
# whole mailbox (and the per-sync message cap isn't used up by job alerts).
_SEARCH_SENDER_TERMS = ATS_SENDER_DOMAINS + ["careers@", "talent@", "recruiting@"]

_SEARCH_SUBJECT_TERMS = [
    '"application received"',
    '"thank you for applying"',
    '"thanks for applying"',
    '"your application"',
    '"application status"',
    '"application update"',
    "interview",
    '"next steps"',
    '"your candidacy"',
    '"pleased to offer"',
    '"excited to offer"',
    "assessment",
    '"received your application"',
    '"application submitted"',
    '"application confirmation"',
    '"thank you for your interest"',
    '"thanks for your interest"',
]

# Gmail's subject:(a b) means both words; these stand in for the intern+application rule.
_SEARCH_INTERN_GROUPS = [
    "(intern application)",
    "(internship application)",
    "(intern offer)",
    "(internship offer)",
    "(intern applied)",
    "(internship applied)",
]

_SEARCH_EXCLUDED_SUBJECTS = [
    '"just posted"',
    '"job matches"',
    '"jobs you might like"',
    '"curated for you"',
    '"is hiring for"',
    '"job alert"',
    '"recommended jobs"',
]


def gmail_search_query() -> str:
    """Gmail search expression mirroring is_candidate_email, so the API pre-filters
    messages before we download or classify anything."""
    senders = " OR ".join(_SEARCH_SENDER_TERMS)
    subjects = " OR ".join(_SEARCH_SUBJECT_TERMS)
    intern_groups = " OR ".join(f"subject:{group}" for group in _SEARCH_INTERN_GROUPS)
    excluded = " OR ".join(_SEARCH_EXCLUDED_SUBJECTS)
    return f"(from:({senders}) OR subject:({subjects}) OR {intern_groups}) -subject:({excluded})"


def _address(sender: str) -> str:
    # The From header arrives as 'Display Name <addr@domain>'. The ^-anchored
    # sender patterns must run against the bare address.
    return parseaddr(sender)[1].lower() or sender.lower()


def _sender_matches(sender: str) -> bool:
    address = _address(sender)
    if any(domain in address for domain in ATS_SENDER_DOMAINS):
        return True
    return any(pattern.search(address) for pattern in TRUSTED_SENDER_PATTERNS)


def _subject_matches(subject: str) -> bool:
    return any(pattern.search(subject) for pattern in SUBJECT_KEYWORDS)


def is_job_alert(subject: str) -> bool:
    return any(pattern.search(subject) for pattern in JOB_ALERT_PATTERNS)


def is_candidate_email(subject: str, sender: str) -> bool:
    """True if this email is plausibly job-application-related and should be sent
    to the LLM for confirmation + extraction."""
    if is_job_alert(subject):
        return False
    return _sender_matches(sender) or _subject_matches(subject)
