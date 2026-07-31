from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

ApplicationStatus = Literal["applied", "interview", "offer", "rejected", "withdrawn", "unknown"]


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None


class ApplicationOut(BaseModel):
    id: str
    company: str
    job_title: str | None = None
    application_date: date | None = None
    status: ApplicationStatus
    gmail_thread_id: str
    raw_snippet: str | None = None
    confidence: float | None = None
    manually_edited: bool
    created_at: datetime
    updated_at: datetime


class ApplicationUpdate(BaseModel):
    company: str | None = None
    job_title: str | None = None
    application_date: date | None = None
    status: ApplicationStatus | None = None


class PaginatedApplications(BaseModel):
    items: list[ApplicationOut]
    total: int
    page: int
    page_size: int
