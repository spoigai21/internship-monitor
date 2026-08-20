"""Parser for Oracle Cloud HCM (Oracle Recruiting) candidate-experience boards.

Used by JPMorgan Chase. The public search endpoint is

    https://<tenant>.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions

driven by a semicolon-delimited ``finder`` expression rather than ordinary query
params. We accept a plain, readable config URL (``?siteNumber=CX_1&keyword=...``)
and build the finder in the fetcher, so ``companies.py`` stays legible.

Note the keyword is fuzzy on Oracle's side ("internship" also matches
"international" and "internal"), which is harmless: the level+cycle title filter
in ``boards.py`` decides what actually alerts.

Requisitions carry a ``PostedDate``, but it is deliberately *not* mapped to
``JobPosting.posted_at``: like every other direct board here, a listing that
first shows up in our diff should alert regardless of how long the employer had
it open. Only the Simplify aggregator is age-filtered.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from monitor.models import JobPosting

_ORACLE_PATH_MARKER = "/hcmrestapi/resources/"
_ORACLE_RESOURCE = "recruitingcejobrequisitions"

# Oracle honours large page sizes; 200 keeps a 2000-req board to ~10 requests.
ORACLE_PAGE_LIMIT = 200

# Facets are requested but unused; omitting the parameter returns an error.
_ORACLE_FACETS = "LOCATIONS"


def is_oracle_recruiting_url(url: str) -> bool:
    lowered = url.lower()
    return _ORACLE_PATH_MARKER in lowered and _ORACLE_RESOURCE in lowered


def oracle_requisitions_url(tenant: str, site_number: str, keyword: str) -> str:
    """Config-facing search URL for one Oracle Recruiting careers site."""
    return (
        f"https://{tenant}.fa.oraclecloud.com/hcmRestApi/resources/latest"
        f"/recruitingCEJobRequisitions?siteNumber={site_number}&keyword={keyword}"
    )


def oracle_site_number(url: str) -> str:
    values = parse_qs(urlparse(url).query).get("siteNumber") or ["CX_1"]
    return values[0] or "CX_1"


def oracle_keyword(url: str) -> str:
    values = parse_qs(urlparse(url).query).get("keyword") or [""]
    return values[0]


def oracle_page_params(url: str, offset: int, limit: int = ORACLE_PAGE_LIMIT) -> dict[str, str]:
    """Query params for one page of the Oracle requisition search.

    ``expand`` is required: without it the response omits ``requisitionList``
    entirely and only the facet envelope comes back.
    """
    finder = (
        "findReqs"
        f";siteNumber={oracle_site_number(url)}"
        f",facetsList={_ORACLE_FACETS}"
        f",limit={limit}"
        f",offset={offset}"
        ",sortBy=POSTING_DATES_DESC"
    )
    keyword = oracle_keyword(url)
    if keyword:
        finder += f",keyword={keyword}"
    return {
        "onlyData": "true",
        "expand": "requisitionList.secondaryLocations",
        "finder": finder,
    }


def oracle_job_url(job_id: str, board_url: str) -> str:
    """Candidate-experience apply URL for one requisition."""
    parsed = urlparse(board_url)
    if not parsed.netloc or not job_id:
        return board_url
    site = oracle_site_number(board_url)
    return (
        f"{parsed.scheme}://{parsed.netloc}"
        f"/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}"
    )


def _requisitions(data: Any) -> list[dict[str, Any]]:
    """Pull the requisition rows out of either a raw or aggregated response."""
    if isinstance(data, dict) and isinstance(data.get("requisitionList"), list):
        return [row for row in data["requisitionList"] if isinstance(row, dict)]
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            rows.extend(r for r in item.get("requisitionList") or [] if isinstance(r, dict))
    return rows


def _location(job: dict[str, Any]) -> str:
    parts = [str(job.get("PrimaryLocation") or "")]
    for secondary in job.get("secondaryLocations") or []:
        if isinstance(secondary, dict):
            parts.append(str(secondary.get("Name") or ""))
        elif secondary:
            parts.append(str(secondary))
    return ", ".join(part for part in parts if part)


def parse_oracle(
    raw_json: str | dict[str, Any],
    company_name: str,
    board_url: str = "",
) -> list[JobPosting]:
    data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    postings: list[JobPosting] = []

    for job in _requisitions(data):
        job_id = job.get("Id")
        if job_id is None:
            continue
        job_id = str(job_id)
        postings.append(
            JobPosting(
                id=job_id,
                title=str(job.get("Title") or ""),
                department=str(job.get("JobFamily") or job.get("Department") or ""),
                location=_location(job),
                url=oracle_job_url(job_id, board_url),
                description=str(job.get("ShortDescriptionStr") or ""),
                company_name=company_name,
            )
        )

    return postings
