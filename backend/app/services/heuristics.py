"""Cheap, zero-cost pre-filter that decides which emails are worth sending to the
LLM extractor.

Deliberately broad (OR, not AND) — a false positive here just costs one extra LLM
call, while a false negative means an application silently never appears.
Sender-domain match covers major ATS platforms; subject-keyword match catches
everything else, including companies that email applicants directly from their own
domain.
"""

import re

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
]


def _sender_matches(sender: str) -> bool:
    sender_lower = sender.lower()
    if any(domain in sender_lower for domain in ATS_SENDER_DOMAINS):
        return True
    return any(pattern.search(sender_lower) for pattern in GENERIC_SENDER_PATTERNS)


def _subject_matches(subject: str) -> bool:
    return any(pattern.search(subject) for pattern in SUBJECT_KEYWORDS)


def is_candidate_email(subject: str, sender: str) -> bool:
    """True if this email is plausibly job-application-related and should be sent
    to the LLM for confirmation + extraction."""
    return _sender_matches(sender) or _subject_matches(subject)
