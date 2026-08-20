"""Parser for SmartRecruiters public posting APIs.

Used by ServiceNow. The board is a plain paginated JSON list:

    https://api.smartrecruiters.com/v1/companies/<Identifier>/postings?limit=100

No auth, no custom headers. ``limit`` caps at 100, so the fetcher walks
``offset`` until ``totalFound`` is covered.

The list endpoint omits ``postingUrl`` (only the per-posting detail endpoint
carries it), but the public apply URL is derivable from the company identifier
and the posting id, so we build it rather than spending one request per job.

``releasedDate`` is deliberately not mapped to ``JobPosting.posted_at``: like
every other direct board here, a listing that first shows up in our diff should
alert regardless of how long it has been open. Only Simplify is age-filtered.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from monitor.models import JobPosting

_SMARTRECRUITERS_HOST = "api.smartrecruiters.com"

# SmartRecruiters rejects limit > 100 on the public postings endpoint.
SMARTRECRUITERS_PAGE_LIMIT = 100


def is_smartrecruiters_url(url: str) -> bool:
    lowered = url.lower()
    return _SMARTRECRUITERS_HOST in lowered and "/postings" in lowered


def smartrecruiters_postings_url(identifier: str) -> str:
    """Config-facing postings URL for one SmartRecruiters company board."""
    return (
        f"https://{_SMARTRECRUITERS_HOST}/v1/companies/{identifier}/postings"
        f"?limit={SMARTRECRUITERS_PAGE_LIMIT}"
    )


def smartrecruiters_identifier(url: str) -> str:
    """Company identifier segment of a postings URL (``.../companies/<id>/...``)."""
    segments = [part for part in urlparse(url).path.split("/") if part]
    if "companies" in segments:
        index = segments.index("companies") + 1
        if index < len(segments):
            return segments[index]
    return ""


def smartrecruiters_job_url(job: dict[str, Any], board_url: str) -> str:
    posting_url = str(job.get("postingUrl") or job.get("applyUrl") or "").strip()
    if posting_url:
        return posting_url
    job_id = str(job.get("id") or "").strip()
    identifier = str((job.get("company") or {}).get("identifier") or "") or (
        smartrecruiters_identifier(board_url)
    )
    if not job_id or not identifier:
        return board_url
    return f"https://jobs.smartrecruiters.com/{identifier}/{job_id}"


def _location(job: dict[str, Any]) -> str:
    location = job.get("location")
    if not isinstance(location, dict):
        return ""
    full = str(location.get("fullLocation") or "").strip()
    if full:
        return full
    parts = [
        str(location.get(field) or "").strip()
        for field in ("city", "region", "country")
    ]
    return ", ".join(part for part in parts if part)


def _label(job: dict[str, Any], field: str) -> str:
    value = job.get(field)
    if isinstance(value, dict):
        return str(value.get("label") or "")
    return str(value or "")


def parse_smartrecruiters(
    raw_json: str | dict[str, Any],
    company_name: str,
    board_url: str = "",
) -> list[JobPosting]:
    data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list):
        return []

    postings: list[JobPosting] = []
    for job in content:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        # Employment type carries "Intern"/"Temporary" on student reqs, and the
        # experience level carries "Student (Undergraduate)" — both feed the
        # level+cycle keyword match when the title alone is ambiguous.
        description = " ".join(
            part
            for part in (
                _label(job, "typeOfEmployment"),
                _label(job, "experienceLevel"),
                _label(job, "function"),
            )
            if part
        )
        postings.append(
            JobPosting(
                id=str(job_id),
                title=str(job.get("name") or ""),
                department=_label(job, "department"),
                location=_location(job),
                url=smartrecruiters_job_url(job, board_url),
                description=description,
                company_name=company_name,
            )
        )

    return postings
