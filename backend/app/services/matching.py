"""Decide whether two (company, job title) pairs describe the same application.

Status emails rarely repeat the company and title exactly as the first email
did: "Humana, Inc." vs "Humana", "JPMorganChase" vs "JPMorgan Chase",
"129778 Software Developer Intern 2027" vs "Software Developer Intern 2027".
Exact matching left rejections as separate rows while the original stayed in
"interview", so matching normalizes both sides first.

Titles match when one's significant words are a SUBSET of the other's. That
merges "Applied AI Engineer Intern, New York" with "2027 Applied AI Engineer
Intern" but keeps genuinely different roles apart ("Cyber Security Summer
Analyst" vs "Production Support Summer Analyst").
"""

import re

_COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "llp", "lp", "corp", "corporation", "co", "company",
    "ltd", "limited", "plc", "group", "gmbh", "sa", "ag", "the",
}

# Words that appear in most internship titles and say nothing about the role.
_TITLE_FILLER = {
    "summer", "winter", "spring", "fall", "intern", "interns", "internship", "internships",
    "program", "programme", "the", "and", "for", "in", "or", "of", "a", "an", "to", "at",
    "position", "role", "opportunity", "opportunities",
}

_DASHES = re.compile(r"[‐-―−]")


def _words(value: str) -> list[str]:
    value = _DASHES.sub("-", value.lower()).replace("&", " and ")
    return re.sub(r"[^\w\s]", " ", value).split()


def company_words(company: str | None) -> list[str]:
    return [w for w in _words(company or "") if w not in _COMPANY_SUFFIXES]


def is_known_company(company: str | None) -> bool:
    words = company_words(company)
    return bool(words) and words != ["unknown"]


def companies_match(a: str | None, b: str | None) -> bool:
    wa, wb = company_words(a), company_words(b)
    if not wa or not wb or ["unknown"] in (wa, wb):
        return False
    if wa == wb or "".join(wa) == "".join(wb):
        return True
    # "Millennium" vs "Millennium Management", "Garmin" vs "Garmin International":
    # the shorter name's words lead the longer one's.
    short, long_ = sorted((wa, wb), key=len)
    return long_[: len(short)] == short


def title_words(title: str | None, *companies: str | None) -> set[str]:
    drop = set(_TITLE_FILLER)
    for company in companies:
        drop.update(company_words(company))
    return {
        w for w in _words(title or "")
        if w not in drop and not any(ch.isdigit() for ch in w)  # years, req IDs, "fy27"
    }


def titles_match(a: str | None, b: str | None, company_a: str | None = None,
                 company_b: str | None = None) -> bool:
    """A missing or generic title (nothing left after normalizing) matches any
    title: follow-up emails often omit the role."""
    wa = title_words(a, company_a, company_b)
    wb = title_words(b, company_a, company_b)
    if not wa or not wb:
        return True
    return wa <= wb or wb <= wa


def title_within(a: str | None, b: str | None, company_a: str | None = None,
                 company_b: str | None = None) -> bool:
    """True if title `a` is the vaguer (or equal) side: its words all appear in `b`."""
    return title_words(a, company_a, company_b) <= title_words(b, company_a, company_b)


def same_application(company_a: str | None, title_a: str | None,
                     company_b: str | None, title_b: str | None) -> bool:
    return companies_match(company_a, company_b) and titles_match(
        title_a, title_b, company_a, company_b
    )
