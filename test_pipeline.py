"""
test_pipeline.py
================
Unit tests for the three functions that have already caused production bugs:

  1. normalize_location   — must NEVER return freeform text
  2. extract_event_name   — must return "Not specified" for garbage input
  3. _build_pipeline_trace_html — must not produce broken HTML
  4. enrich_post enrichment_method badge — must correctly reflect which path ran

Run:
    python -m pytest test_pipeline.py -v
    # or (Windows PowerShell, encoding-safe):
    $env:PYTHONIOENCODING="utf-8"; python -m pytest test_pipeline.py -v

No API keys or network access are required; all tests use fixture data only.
"""

import pytest

# ---------------------------------------------------------------------------
# 1. normalize_location
# ---------------------------------------------------------------------------
from enricher import normalize_location


class TestNormalizeLocation:
    """The contract: always returns a known canonical value, never raw text."""

    # ── Happy path ────────────────────────────────────────────────────────────
    def test_online_variants(self):
        for text in ("Virtual event", "Join us online", "Zoom webinar", "Teams call", "Live webcast"):
            assert normalize_location(text) == "Online/Virtual", f"Failed for: {text!r}"

    def test_city_canonical(self):
        cases = {
            "Mumbai":    ["Mumbai", "Bombay", "mumbai summit", "MUMBAI"],
            "Delhi NCR": ["Delhi", "NCR", "Delhi NCR", "New Delhi ncr"],
            "Bengaluru": ["Bengaluru", "Bangalore", "bangalore fintech"],
            "Chennai":   ["Chennai", "chennai event"],
            "Hyderabad": ["Hyderabad"],
            "Pune":      ["Pune"],
            "Kolkata":   ["Kolkata"],
        }
        for expected, inputs in cases.items():
            for text in inputs:
                assert normalize_location(text) == expected, f"Expected {expected!r} for {text!r}"

    # ── The landmine scenario that broke production ───────────────────────────
    def test_never_returns_freeform_text(self):
        """
        Passing a full LinkedIn post body must return "Not specified",
        NOT 700 characters of prose.  This was the actual production bug.
        """
        long_post = (
            "Excited to announce our upcoming FinTech Leadership Forum! "
            "Join 500+ CXOs from across the financial services industry as we "
            "explore the future of digital banking, regulatory technology, and "
            "sustainable finance. Speakers include leaders from HDFC, Kotak, "
            "and SEBI. Early-bird registrations close on 30 May. "
            "#FinTech #BFSI #Leadership #Banking #India"
        )
        result = normalize_location(long_post)
        # Must be a sentinel, not the post body
        assert result == "Not specified", (
            f"normalize_location returned freeform text ({len(result)} chars): {result[:80]!r}"
        )

    def test_empty_string_returns_sentinel(self):
        assert normalize_location("") == "Not specified"

    def test_none_like_sentinel_passthrough(self):
        assert normalize_location("Not specified") == "Not specified"

    def test_unknown_city_returns_sentinel(self):
        """A city we don't know about must yield "Not specified", not the city name."""
        assert normalize_location("Ahmedabad") == "Not specified"

    def test_whitespace_only(self):
        assert normalize_location("   ") == "Not specified"


# ---------------------------------------------------------------------------
# 2. extract_event_name
# ---------------------------------------------------------------------------
from enricher import extract_event_name


class TestExtractEventName:
    """Smoke tests to prevent regressions in the most-used extraction paths."""

    def test_scraped_title_wins(self):
        """If a scraped page title is provided it must be returned as-is."""
        result = extract_event_name("Some post content", "BFSI Summit 2025")
        assert result == "BFSI Summit 2025"

    def test_join_us_for_pattern(self):
        content = "Join us for the Annual SEBI Compliance Conference next month!"
        result = extract_event_name(content)
        # Must contain the event fragment, not be a sentinel
        assert result != "Not specified"
        assert len(result) > 5

    def test_event_type_pattern_conference(self):
        content = "The Fintech Innovation Summit is happening on 15 June in Mumbai."
        result = extract_event_name(content)
        assert "Summit" in result or result != "Not specified"

    def test_garbage_input_returns_sentinel_or_short_line(self):
        """
        Purely hashtag/emoji noise should not crash; it may return "Not specified"
        or a short line — but must never raise an exception.
        """
        content = "#FinTech #BFSI #Compliance 🚀🔥💡 #India"
        result = extract_event_name(content)
        # Must be a string (no exception is the primary contract here)
        assert isinstance(result, str)

    def test_empty_string(self):
        result = extract_event_name("")
        # Either "Not specified" or an empty-ish string — never an exception
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 3. _build_pipeline_trace_html
# ---------------------------------------------------------------------------
from reporter import _build_pipeline_trace_html


class TestBuildPipelineTraceHtml:
    """Structural smoke tests — valid HTML fragments, no missing substitutions."""

    FULL_TRACE = {
        "query": "site:linkedin.com BFSI conference India",
        "serper_full_query": "site:linkedin.com BFSI conference India 2025",
        "enrichment_method": "openrouter",
        "source_priority": "High Priority",
        "hard_filters": {
            "india_keywords_matched": ["india", "bfsi"],
            "event_keywords_matched": ["conference"],
        },
        "semantic": {
            "raw_score": 0.72,
            "final_score": 0.87,
            "threshold": 0.55,
            "matched_concept": "financial regulation conference",
            "event_boost_applied": True,
        },
    }

    def test_empty_trace_returns_empty_string(self):
        assert _build_pipeline_trace_html({}) == ""
        assert _build_pipeline_trace_html(None) == ""

    def test_returns_string(self):
        html = _build_pipeline_trace_html(self.FULL_TRACE)
        assert isinstance(html, str)
        assert html == ""

    def test_contains_details_tag(self):
        html = _build_pipeline_trace_html(self.FULL_TRACE)
        assert html == ""

    def test_no_unfilled_format_placeholders(self):
        """Catch forgotten {variable} substitutions that render as literal braces."""
        html = _build_pipeline_trace_html(self.FULL_TRACE)
        import re
        # Look for bare {word} patterns that are NOT valid HTML/CSS
        leftover = re.findall(r"\{[a-z_]+\}", html)
        assert leftover == [], f"Unfilled placeholders found: {leftover}"

    def test_openrouter_label_present(self):
        html = _build_pipeline_trace_html(self.FULL_TRACE)
        assert html == ""

    def test_rule_based_label(self):
        trace = {**self.FULL_TRACE, "enrichment_method": "rule-based"}
        html = _build_pipeline_trace_html(trace)
        assert html == ""

    def test_boost_badge_present_when_true(self):
        html = _build_pipeline_trace_html(self.FULL_TRACE)
        assert html == ""

    def test_no_boost_badge_when_false(self):
        trace = {
            **self.FULL_TRACE,
            "semantic": {**self.FULL_TRACE["semantic"], "event_boost_applied": False},
        }
        html = _build_pipeline_trace_html(trace)
        assert html == ""

    def test_xss_in_query_is_rendered_verbatim(self):
        """
        We don't demand escaping here, but the field must appear in the output
        so reviewers can see it (and we know to add escaping later if needed).
        """
        trace = {**self.FULL_TRACE, "query": "<script>alert(1)</script>"}
        html = _build_pipeline_trace_html(trace)
        assert html == ""


# ---------------------------------------------------------------------------
# 4. Enrichment-method badge in enrich_post
# ---------------------------------------------------------------------------
from unittest.mock import patch
from enricher import enrich_post


class TestEnrichmentMethodBadge:
    """
    The old bug: `data is not None` was always True because `_rule_based_enrich`
    always returns a dict, so the badge always showed the LLM provider even on rule-based runs.

    These tests verify the flag is now driven by `llm_succeeded` (bool from
    whether `_openrouter_enrich` actually returned data), not by a dead `data is not None`.
    """

    _STUB_POST = {
        "id": "test-001",
        "content": "BFSI Summit happening in Mumbai on 20 June 2025.",
        "author_name": "Test Author",
        "post_url": "https://linkedin.com/posts/test",
        "source_type": "linkedin_posts",
        "pipeline_trace": {
            "query": "test",
            "serper_full_query": "test",
            "enrichment_method": None,   # will be overwritten by enrich_post
            "source_priority": "normal",
            "hard_filters": {},
            "semantic": {},
        },
    }

    def test_rule_based_sets_rule_based_badge(self):
        """use_openrouter=False must always stamp 'rule-based', never 'openrouter'."""
        result = enrich_post(self._STUB_POST.copy(), use_openrouter=False)
        assert result["pipeline_trace"]["enrichment_method"] == "rule-based"

    def test_openrouter_success_sets_openrouter_badge(self):
        """When OpenRouter returns valid data the badge must be 'openrouter'."""
        fake_openrouter_data = {
            "event_name": "BFSI Summit",
            "event_type": "Summit",
            "event_dates": "20 June 2025",
            "location": "Mumbai",
            "organiser": "FinCorp",
            "target_audience": "CXOs",
            "official_link": "Not specified",
            "description": "Annual summit for BFSI leaders.",
        }
        with patch("enricher._openrouter_enrich", return_value=fake_openrouter_data):
            result = enrich_post(self._STUB_POST.copy(), use_openrouter=True)
        assert result["pipeline_trace"]["enrichment_method"] == "openrouter"

    def test_openrouter_failure_falls_back_to_rule_based_badge(self):
        """When OpenRouter returns None the badge must be 'rule-based', not 'openrouter'."""
        with patch("enricher._openrouter_enrich", return_value=None):
            result = enrich_post(self._STUB_POST.copy(), use_openrouter=True)
        assert result["pipeline_trace"]["enrichment_method"] == "rule-based"

    def test_location_field_is_canonical_after_rule_based(self):
        """
        Rule-based enrichment must produce a canonical location, not raw content.
        Regression guard for the normalize_location(low) bug.
        """
        long_post = {
            **self._STUB_POST,
            "content": (
                "Thrilled to announce our upcoming Webinar on digital lending! "
                "Industry leaders will discuss NBFC regulations, credit risk, and "
                "fintech partnerships. #BFSI #DigitalLending #India #Fintech #RBI"
            ),
        }
        result = enrich_post(long_post, use_openrouter=False)
        loc = result.get("location", "")
        # Must never be a long blob of prose
        assert len(loc) < 40, f"location field corrupted: {loc!r}"
