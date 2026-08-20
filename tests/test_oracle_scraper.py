"""Tests for the Oracle Recruiting (JPMorgan Chase) board parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor.companies import INTERN_CYCLE_KEYWORDS, INTERN_LEVEL_KEYWORDS
from monitor.parsers.boards import (
    BoardType,
    detect_board_type,
    job_matches_level_and_cycle,
    parse_job_board,
)
from monitor.parsers.oracle import (
    ORACLE_PAGE_LIMIT,
    is_oracle_recruiting_url,
    oracle_job_url,
    oracle_page_params,
    oracle_requisitions_url,
    parse_oracle,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
BOARD_URL = oracle_requisitions_url("jpmc", "CX_1", "internship")


@pytest.fixture
def sample() -> str:
    return (FIXTURES_DIR / "oracle_sample.json").read_text()


class TestOracleUrls:
    def test_detects_board_type(self) -> None:
        assert is_oracle_recruiting_url(BOARD_URL)
        assert detect_board_type(BOARD_URL) == BoardType.ORACLE

    def test_greenhouse_url_is_not_oracle(self) -> None:
        assert not is_oracle_recruiting_url(
            "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
        )

    def test_page_params_carry_site_keyword_and_offset(self) -> None:
        params = oracle_page_params(BOARD_URL, offset=400)

        # expand is mandatory: without it Oracle omits requisitionList entirely.
        assert params["expand"] == "requisitionList.secondaryLocations"
        finder = params["finder"]
        assert "siteNumber=CX_1" in finder
        assert f"limit={ORACLE_PAGE_LIMIT}" in finder
        assert "offset=400" in finder
        assert "keyword=internship" in finder

    def test_page_params_omit_empty_keyword(self) -> None:
        finder = oracle_page_params(
            oracle_requisitions_url("jpmc", "CX_1", ""), offset=0
        )["finder"]

        assert "keyword=" not in finder

    def test_job_url_points_at_candidate_experience_site(self) -> None:
        assert oracle_job_url("210773759", BOARD_URL) == (
            "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en"
            "/sites/CX_1/job/210773759"
        )


class TestParseOracle:
    def test_maps_requisition_fields(self, sample: str) -> None:
        jobs = parse_oracle(sample, "JPMorgan Chase", board_url=BOARD_URL)

        assert len(jobs) == 3
        job = jobs[0]
        assert job.id == "210773759"
        assert job.title == (
            "2027 Code for Good Hackathon - Software Engineer Program"
            " - Summer Internship – United States"
        )
        assert job.company_name == "JPMorgan Chase"
        assert job.url.endswith("/sites/CX_1/job/210773759")

    def test_flattens_secondary_locations(self, sample: str) -> None:
        job = parse_oracle(sample, "JPMorgan Chase", board_url=BOARD_URL)[0]

        assert job.location.startswith("Chicago, IL, United States")
        assert "New York, NY, United States" in job.location

    def test_accepts_the_raw_items_envelope(self, sample: str) -> None:
        raw = {"items": [json.loads(sample)]}

        assert len(parse_oracle(raw, "JPMorgan Chase", board_url=BOARD_URL)) == 3

    def test_skips_rows_without_an_id(self) -> None:
        raw = {"requisitionList": [{"Title": "Summer Internship 2027"}]}

        assert parse_oracle(raw, "JPMorgan Chase") == []

    def test_dispatches_through_parse_job_board(self, sample: str) -> None:
        jobs = parse_job_board(sample, BOARD_URL, "JPMorgan Chase")

        assert [job.id for job in jobs] == [
            job.id for job in parse_oracle(sample, "JPMorgan Chase", board_url=BOARD_URL)
        ]

    def test_only_intern_cycle_titles_match(self, sample: str) -> None:
        jobs = parse_oracle(sample, "JPMorgan Chase", board_url=BOARD_URL)
        matched = [
            job.title
            for job in jobs
            if job_matches_level_and_cycle(
                job, INTERN_LEVEL_KEYWORDS, INTERN_CYCLE_KEYWORDS
            )
        ]

        # Oracle's keyword search is fuzzy — "internship" also returns
        # "International" and "Internal" roles, which the title filter drops.
        assert len(matched) == 2
        assert not any("International Private Bank" in title for title in matched)
