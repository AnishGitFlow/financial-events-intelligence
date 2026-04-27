"""
config.py - Central configuration for the Indian AMC/AIF/PMS Compliance Signal Monitor
Updated to remove the SERPER API query restriction.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ─────────────────────────────────────────────────────────────────────
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

# ── Email Delivery (Microsoft 365 / Outlook) ─────────────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
REPORT_TO     = os.getenv("REPORT_TO", "")
REPORT_FROM   = os.getenv("REPORT_FROM", SMTP_USER)

# ── Scheduler ─────────────────────────────────────────────────────────────────────
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "08:00")  # 24-hr IST

# ── API Usage Settings ────────────────────────────────────────────────────────────
# Set to None to process ALL search queries every run.
# If you later want throttling again, set a numeric value like 5 or 10.
DAILY_QUERY_LIMIT = None

# Gemini processing limits
TOP_POSTS_FOR_LLM = 5
MAX_CHARS_FOR_LLM = 700

# ── Semantic Engine Settings ──────────────────────────────────────────────────────
# Cosine similarity threshold (0.0–1.0). Posts below this are discarded.
# 0.35 = permissive (more posts pass), 0.50 = strict (only high-match posts pass)
# Increased slightly to reduce noisy posts.
# Recommended range:
# 0.40 = balanced
# 0.45 = strict high-intent filtering
SEMANTIC_THRESHOLD = 0.42

# ==============================================================================
# TARGET CONCEPTS
# ==============================================================================

TARGET_CONCEPTS = {

    "Industry Conference": (
        "A large-scale gathering or conference focused on the Indian AMC, AIF, PMS, "
        "or wealth management industries. Includes discussions on market trends, "
        "regulations, and investment strategies."
    ),

    "Leadership Summit": (
        "A high-level summit for CXOs, founders, and senior leaders in the financial "
        "services sector, specifically focusing on asset and wealth management in India."
    ),

    "Educational Webinar": (
        "An online webinar or virtual session providing educational content, market "
        "outlooks, or technical discussions for finance professionals and wealth advisors."
    ),

    "Professional Workshop": (
        "An interactive training or workshop designed for skill enhancement in portfolio "
        "management, financial advisory, or wealthtech."
    ),

    "Networking Meetup": (
        "An informal or formal networking event, meetup, or mixer for professionals "
        "in the financial advisory, wealth management, or investment industries."
    ),

    "Investment Industry Event": (
        "A general gathering, seminar, or event focused on the broader investment "
        "industry, including alternative investments and portfolio management."
    ),

    "Wealth Management Event": (
        "An event, roundtable, or discussion panel specifically tailored to wealth "
        "managers, family offices, and financial advisors."
    ),

    "Financial Advisory Event": (
        "A seminar, workshop, or conference catering to mutual fund distributors (MFDs), "
        "registered investment advisors (RIAs), and financial planners."
    ),
}

# ==============================================================================
# HARD FILTERS
# ==============================================================================

# More permissive India relevance filter.
# Avoids dropping useful operational posts that don't explicitly mention India.
INDIA_HARD_SIGNALS = [
    "india", "indian", "sebi", "amfi", "rbi", "pmla", "dpdp",
    "aif", "pms", "amc", "mutual fund", "wealth management",
    "asset management", "fund house", "investment management",
    "nse", "bse", "compliance", "audit", "regulatory",
]

EVENT_HARD_SIGNALS = [
    "upcoming event", "event registration", "speaker announcement",
    "event invitation", "industry gathering", "networking event",
    "educational session", "register now", "conference", "summit",
    "webinar", "workshop", "meetup", "panel discussion"
]

EXCLUDE_KEYWORDS = [

    # Non-India regulations
    "us sec",
    "sec filing",
    "finra",
    "mifid",
    "european union",
    "us regulation",

    # Spam / low-intent hiring
    "walk-in interview",
    "mass hiring",
    "certificate course",
    "training program",

    # Generic engagement bait
    "like and share",
    "subscribe now",
]

# ==============================================================================
# SOURCE PRIORITY
# ==============================================================================

HIGH_PRIORITY_SOURCES = [
    "morningstar", "morningstar india", "business standard", "business standard events",
    "networkfp", "cafe mutual", "pms bazaar", "pms aif world",
    "financial freedom fraternity", "cfa society india", "equalifi",
    "moneycontrol", "aafm india", "association of portfolio managers in india", "hubbis"
]

MEDIUM_PRIORITY_SOURCES = [
    "amc", "aif", "pms", "asset management", "investment management",
    "mutual fund", "fund house", "wealth management",
    "fintech", "investment advisory", "wealthtech", "capital markets",
]

# ==============================================================================
# EVENT NORMALIZATION
# ==============================================================================

EVENT_NORMALIZATION_MAPPINGS = {
    "conference": "Conference",
    "seminar": "Conference",
    "summit": "Summit",
    "conclave": "Summit",
    "webinar": "Webinar",
    "virtual event": "Webinar",
    "online session": "Webinar",
    "workshop": "Workshop",
    "training": "Workshop",
    "masterclass": "Workshop",
    "meetup": "Meetup",
    "networking": "Meetup",
    "mixer": "Meetup"
}

# ==============================================================================
# SENIORITY FILTER
# ==============================================================================

SENIOR_TITLES = [
    "cxo", "ceo", "cfo", "coo", "cto", "cro", "chief",
    "founder", "co-founder", "director", "managing director",
    "vp", "vice president", "head", "principal", "partner",
]

# ==============================================================================
# SEARCH QUERIES
# Tailored specifically for discovering event announcements.
# ==============================================================================

SEARCH_QUERIES = [

    # --------------------------------------------------------------------------
    # Conferences and Summits
    # --------------------------------------------------------------------------
    "AMC conference India",
    "wealth management summit India",
    "portfolio management conference",
    "register now investment summit",
    "mutual fund distributor conference",
    "investment banking summit India",
    "AIF PMS conclave",

    # --------------------------------------------------------------------------
    # Webinars and Virtual Events
    # --------------------------------------------------------------------------
    "AIF webinar India",
    "wealthtech webinar",
    "online investment seminar India",

    # --------------------------------------------------------------------------
    # Meetups and Workshops
    # --------------------------------------------------------------------------
    "PMS meetup India",
    "investment advisory workshop",
    "financial services networking event",
    "wealth management panel discussion",
    "financial planning seminar India",
    "CFA investment event India",

    # --------------------------------------------------------------------------
    # High-Intent Conversational Queries
    # --------------------------------------------------------------------------
    "join us at our upcoming conference",
    "excited to speak at the wealth management summit",
    "register for our exclusive investment webinar",
    "looking forward to the financial advisory workshop",
    "networking with industry leaders at the meetup",
]

# ==============================================================================
# OPTIONAL HELPER FUNCTION
# ==============================================================================

def get_active_queries():
    """
    Returns all search queries if DAILY_QUERY_LIMIT is None.
    Otherwise returns a limited subset.
    """

    if DAILY_QUERY_LIMIT is None:
        return SEARCH_QUERIES

    return SEARCH_QUERIES[:DAILY_QUERY_LIMIT]


# ==============================================================================
# BACKWARD-COMPATIBLE QUERY ROTATION FUNCTION
# ==============================================================================

def get_daily_queries(day=0):
    """
    Returns active search queries.

    If DAILY_QUERY_LIMIT is None:
        returns ALL queries.

    Otherwise:
        rotates queries daily to reduce SERPER usage.
    """

    if DAILY_QUERY_LIMIT is None:
        return SEARCH_QUERIES

    start = (day * DAILY_QUERY_LIMIT) % len(SEARCH_QUERIES)
    end = start + DAILY_QUERY_LIMIT

    if end <= len(SEARCH_QUERIES):
        return SEARCH_QUERIES[start:end]

    return SEARCH_QUERIES[start:] + SEARCH_QUERIES[: end - len(SEARCH_QUERIES)]
