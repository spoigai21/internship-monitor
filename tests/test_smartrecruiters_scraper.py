"""Tests for the SmartRecruiters (ServiceNow) board parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from monitor.parsers.boards import BoardType, detect_board_type, parse_job_board
from monitor.parsers.smartrecruiters import (
    SMARTRECRUITERS_PAGE_LIMIT,
    is_smartrecruiters_url,
    parse_smartrecruiters,
    smartrecruiters_identifier,
    smartrecruiters_postings_url,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
BOARD_URL = smartrecruiters_postings_url("ServiceNow")


@pytest.fixture
def sample() -> str:
    return (FIXTURES_DIR / "smartrecruiters_sample.json").read_text()


class TestSmartRecruitersUrls:
    def test_detects_board_type(self) -> None:
        assert is_smartrecruiters_url(BOARD_URL)
        assert detect_board_type(BOARD_URL) == BoardType.SMARTRECRUITERS

    def test_postings_url_requests_the_max_page_size(self) -> None:
        assert BOARD_URL == (
            "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings"
            f"?limit={SMARTRECRUITERS_PAGE_LIMIT}"
        )

    def test_extracts_company_identifier(self) -> None:
        assert smartrecruiters_identifier(BOARD_URL) == "ServiceNow"
        assert smartrecruiters_identifier("https://example.com/postings") == ""


class TestParseSmartRecruiters:
    def test_maps_posting_fields(self, sample: str) -> None:
        jobs = parse_smartrecruiters(sample, "ServiceNow", board_url=BOARD_URL)

        assert len(jobs) == 3
        job = jobs[0]
        assert job.id == "744000143436369"
        assert job.title == "Intern - Marketing Associate"
        assert job.company_name == "ServiceNow"
        assert job.location

    def test_builds_the_public_apply_url(self, sample: str) -> None:
        job = parse_smartrecruiters(sample, "ServiceNow", board_url=BOARD_URL)[0]

        # The list endpoint omits postingUrl, so it is derived from the id.
        assert job.url == f"https://jobs.smartrecruiters.com/ServiceNow/{job.id}"

    def test_prefers_an_explicit_posting_url(self) -> None:
        raw = {
            "content": [
                {
                    "id": "1",
                    "name": "Software Engineering Intern",
                    "postingUrl": "https://jobs.smartrecruiters.com/ServiceNow/1-swe",
                }
            ]
        }

        job = parse_smartrecruiters(raw, "ServiceNow", board_url=BOARD_URL)[0]

        assert job.url == "https://jobs.smartrecruiters.com/ServiceNow/1-swe"

    def test_description_carries_employment_and_experience_labels(self) -> None:
        raw = {
            "content": [
                {
                    "id": "1",
                    "name": "University Program",
                    "typeOfEmployment": {"label": "Intern"},
                    "experienceLevel": {"label": "Student (Undergraduate)"},
                }
            ]
        }

        job = parse_smartrecruiters(raw, "ServiceNow")[0]

        assert "Intern" in job.description
        assert "Student (Undergraduate)" in job.description

    def test_falls_back_to_city_region_country(self) -> None:
        raw = {
            "content": [
                {
                    "id": "1",
                    "name": "Intern",
                    "location": {"city": "Santa Clara", "region": "CA", "country": "us"},
                }
            ]
        }

        assert parse_smartrecruiters(raw, "ServiceNow")[0].location == (
            "Santa Clara, CA, us"
        )

    def test_skips_rows_without_an_id(self) -> None:
        assert parse_smartrecruiters({"content": [{"name": "Intern"}]}, "ServiceNow") == []

    def test_returns_empty_for_a_malformed_body(self) -> None:
        assert parse_smartrecruiters({"totalFound": 0}, "ServiceNow") == []

    def test_dispatches_through_parse_job_board(self, sample: str) -> None:
        jobs = parse_job_board(sample, BOARD_URL, "ServiceNow")

        assert len(jobs) == 3
        assert jobs[0].url.startswith("https://jobs.smartrecruiters.com/ServiceNow/")
