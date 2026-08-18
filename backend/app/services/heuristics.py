"""Cheap, zero-cost pre-filter that decides which emails are worth sending to the
LLM extractor.

Deliberately broad (OR, not AND) — a false positive here just costs one extra LLM
call, while a false negative means an application silently never appears.
Sender-domain match covers major ATS platforms; subject-keyword match catches
everything else, including companies that email applicants directly from their own
domain.
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

GENERIC_SENDER_PATTERNS = [
    re.compile(r"^noreply@", re.IGNORECASE),
    re.compile(r"^no-reply@", re.IGNORECASE),
    re.compile(r"^careers@", re.IGNORECASE),
    re.compile(r"^talent@", re.IGNORECASE),
    re.compile(r"^recruiting@", re.IGNORECASE),
]

SUBJECT_KEYWORDS = [
    re.compile(r"application received", re.IGNORECASE),
    re.compile(r"thank you for applying", re.IGNORECASE),
    re.compile(r"thanks for applying", re.IGNORECASE),
    re.compile(r"your application (to|for|at)", re.IGNORECASE),
    re.compile(r"application status", re.IGNORECASE),
    re.compile(r"application update", re.IGNORECASE),
    re.compile(r"interview", re.IGNORECASE),
    re.compile(r"next steps", re.IGNORECASE),
    re.compile(r"we('re| are) (excited|pleased) to offer", re.IGNORECASE),
    re.compile(r"moving forward with other candidates", re.IGNORECASE),
    re.compile(r"your candidacy", re.IGNORECASE),
    re.compile(r"\bintern(ship)?\b", re.IGNORECASE),
    re.compile(r"received your application", re.IGNORECASE),
    re.compile(r"\bassessment\b", re.IGNORECASE),
    re.compile(r"coding (challenge|test)", re.IGNORECASE),
    re.compile(r"hirevue", re.IGNORECASE),
]

# Plain-text equivalents of the patterns above, used to build the server-side Gmail
# search query so manual sync only lists plausibly relevant messages instead of the
# whole mailbox. `noreply@`-style senders are deliberately excluded: nearly all
# automated mail matches them, which would make the search useless as a filter --
# the local sender check still catches those among whatever the query returns.
_SEARCH_SENDER_TERMS = ATS_SENDER_DOMAINS + ["careers@", "talent@", "recruiting@"]

_SEARCH_SUBJECT_TERMS = [
    '"application received"',
    '"thank you for applying"',
    '"thanks for applying"',
    '"your application"',
    '"application status"',
    '"application update"',
    "interview",
    "internship",
    "intern",
    '"next steps"',
    '"your candidacy"',
    '"pleased to offer"',
    '"excited to offer"',
    "assessment",
    '"received your application"',
]


def gmail_search_query() -> str:
    """Gmail search expression mirroring is_candidate_email, so the API pre-filters
    messages before we download or classify anything."""
    senders = " OR ".join(_SEARCH_SENDER_TERMS)
    subjects = " OR ".join(_SEARCH_SUBJECT_TERMS)
    return f"(from:({senders}) OR subject:({subjects}))"


def _sender_matches(sender: str) -> bool:
    # The From header arrives as 'Display Name <addr@domain>'. The ^-anchored
    # generic patterns must run against the bare address -- against the full
    # header they would never match anything.
    address = parseaddr(sender)[1].lower() or sender.lower()
    if any(domain in address for domain in ATS_SENDER_DOMAINS):
        return True
    return any(pattern.search(address) for pattern in GENERIC_SENDER_PATTERNS)


def _subject_matches(subject: str) -> bool:
    return any(pattern.search(subject) for pattern in SUBJECT_KEYWORDS)


def is_candidate_email(subject: str, sender: str) -> bool:
    """True if this email is plausibly job-application-related and should be sent
    to the LLM for confirmation + extraction."""
    return _sender_matches(sender) or _subject_matches(subject)
