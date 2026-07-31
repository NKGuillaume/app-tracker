from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class EmailExtraction(BaseModel):
    is_job_application_email: bool = Field(
        description=(
            "True only if this email is genuinely about a job application the "
            "recipient submitted (confirmation, status update, interview, offer, "
            "rejection). False for job alerts, newsletters, marketing, or recruiter "
            "cold outreach with no prior application."
        )
    )
    company: str | None = Field(default=None, description="Hiring company name, or null if unclear")
    job_title: str | None = Field(default=None, description="Job title applied for, or null if unclear")
    application_date: date | None = Field(
        default=None,
        description=(
            "Date the application was submitted, if inferable from the email content "
            "or send date; otherwise null"
        ),
    )
    status: Literal["applied", "interview", "offer", "rejected", "withdrawn", "unknown"] = "unknown"
    confidence: float = Field(ge=0, le=1, description="Model's confidence in this classification")
