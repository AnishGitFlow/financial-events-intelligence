"""
Central configuration for the Financial Services Event Intelligence Pipeline.

Design principle:
Good queries + strict gates beat fuzzy scoring.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- API keys ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Financial Events Pipeline")
OPENROUTER_MODELS = [
    model.strip()
    for model in os.getenv(
        "OPENROUTER_MODELS",
        "openai/gpt-oss-120b:free,"
        "deepseek/deepseek-v4-flash:free,"
        "z-ai/glm-4.5-air:free,"
        "mistralai/mistral-7b-instruct:free,"
        "meta-llama/llama-3-8b-instruct:free",
    ).split(",")
    if model.strip()
]

# --- Email delivery ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
REPORT_TO = os.getenv("REPORT_TO", "")
REPORT_FROM = os.getenv("REPORT_FROM", SMTP_USER)

# --- Scheduler ---
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "08:00")

# --- Search and API usage ---
DAILY_QUERY_LIMIT = None
SERPER_RECENCY = os.getenv("SERPER_RECENCY", "day")
SERPER_TBS_BY_RECENCY = {
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
}

# --- LLM enrichment limits ---
TOP_POSTS_FOR_LLM = 5
MAX_CHARS_FOR_LLM = 700

# --- Source labels ---
SOURCE_TYPE_LABELS = {
    "linkedin_posts": "LinkedIn posts",
    "official_event_pages": "Official/event pages",
    "registration_pages": "Registration pages",
    "industry_bodies": "Industry bodies",
    "company_pages": "Company pages",
    "media_pr": "Media/PR",
    "community_events": "Community/open web",
    "open_web_discovery": "Open-web discovery",
}

# --- Trusted / known domains for source inference ---
REGISTRATION_DOMAINS = [
    "townscript.com", "eventbrite.", "allevents.in", "meraevents.com",
    "explara.com", "bookmyshow.com", "zoom.us", "gotowebinar.com",
    "events.microsoft.com", "airmeet.com", "hubilo.com", "10times.com",
    "cvent.com",
]

COMMUNITY_EVENT_DOMAINS = [
    "lu.ma", "meetup.com",
]

INDUSTRY_BODY_DOMAINS = [
    "amfiindia.com", "cfasocietyindia.org", "fpsbindia.org", "nism.ac.in",
    "sebi.gov.in", "nseindia.com", "bseindia.com", "nsdl.co.in",
    "cdslindia.com", "ivca.in", "ficci.in", "cii.in", "assocham.org",
    "phdcci.in", "imcnet.org",
]

MEDIA_PR_DOMAINS = [
    "bfsi.economictimes.indiatimes.com", "economictimes.indiatimes.com",
    "moneycontrol.com", "business-standard.com", "livemint.com",
    "financialexpress.com", "cnbctv18.com", "prnewswire.com",
    "businesswireindia.com", "aninews.in", "apnnews.com", "mediabrief.com",
]

COMPANY_DOMAINS = [
    "hdfcfund.com", "icicipruamc.com", "sbimf.com", "kotakmf.com",
    "mutualfund.adityabirlacapital.com", "nipponindiamf.com",
    "axismf.com", "miraeassetmf.co.in", "dspim.com", "nuvama.com",
    "360.one", "motilaloswalmf.com", "askfinancials.com", "marcellus.in",
    "whiteoakamc.com", "helioscapital.in", "alchemycapital.com",
    "pmsbazaar.com", "pmsaifworld.com", "cafemutual.com", "networkfp.com",
]

INDIA_FOCUSED_DOMAINS = (
    REGISTRATION_DOMAINS
    + INDUSTRY_BODY_DOMAINS
    + COMPANY_DOMAINS
    + ["in", ".co.in", ".org.in", "indiatimes.com"]
)

# --- Hard filter vocabulary ---
FINANCE_DOMAIN_SIGNALS = [
    "wealth", "wealth management", "wealth manager", "wealth advisor",
    "private wealth", "private banking", "family office", "family offices",
    "hni", "uhni", "amc", "asset management", "mutual fund",
    "fund manager", "pms", "portfolio management", "aif",
    "alternative investment", "alternate investment", "ria",
    "investment adviser", "investment advisor", "investment advisory",
    "financial advisor", "financial adviser", "financial planning",
    "distributor", "mfd", "ifa", "bfsi", "fintech", "capital markets",
    "sebi", "amfi", "nism", "nse", "bse",
]

EVENT_HARD_SIGNALS = [
    "summit", "conference", "conclave", "webinar", "seminar", "panel",
    "workshop", "register", "registration", "join us", "speaker",
    "speakers", "agenda", "fireside chat", "roundtable", "meetup",
    "forum", "symposium", "masterclass", "event", "session",
]

INDIA_LOCATION_SIGNALS = [
    "india", "indian", "mumbai", "delhi", "new delhi", "bengaluru",
    "bangalore", "chennai", "hyderabad", "pune", "kolkata", "ahmedabad",
    "gift city", "gurgaon", "gurugram", "noida", "navi mumbai",
]

EXCLUDE_KEYWORDS = [
    "walk-in interview", "mass hiring", "job opening", "we are hiring",
    "certificate course", "certification course", "like and share",
    "subscribe now",
]

NEGATIVE_SIGNALS = [
    "telecom", "servicenow", "climate adaptation", "net zero",
    "houston ecosystem", "female founders", "cybersecurity",
    "corporate governance", "generic tech meetup", "startup meetup",
    "sam conference", "us sec", "sec filing", "finra", "mifid",
    "european union", "us regulation",
]

# --- Event normalization ---
EVENT_NORMALIZATION_MAPPINGS = {
    "conference": "Conference",
    "seminar": "Conference",
    "summit": "Summit",
    "conclave": "Summit",
    "forum": "Summit",
    "symposium": "Conference",
    "webinar": "Webinar",
    "virtual event": "Webinar",
    "online session": "Webinar",
    "workshop": "Workshop",
    "training": "Workshop",
    "masterclass": "Workshop",
    "meetup": "Meetup",
    "networking": "Meetup",
    "mixer": "Meetup",
}

# --- Source-aware queries ---
SEARCH_SOURCE_QUERIES = [
    # Trusted site queries
    {"source_type": "linkedin_posts", "query_mode": "trusted_site", "query": "site:linkedin.com/posts AIF PMS conclave India"},
    {"source_type": "linkedin_posts", "query_mode": "trusted_site", "query": "site:linkedin.com/posts wealth management summit India"},
    {"source_type": "linkedin_posts", "query_mode": "trusted_site", "query": "site:linkedin.com/posts mutual fund distributor event India"},
    {"source_type": "registration_pages", "query_mode": "trusted_site", "query": "site:townscript.com wealth management summit India"},
    {"source_type": "registration_pages", "query_mode": "trusted_site", "query": "site:eventbrite.com investment webinar India"},
    {"source_type": "registration_pages", "query_mode": "trusted_site", "query": "site:allevents.in investment seminar India"},
    {"source_type": "community_events", "query_mode": "trusted_site", "query": "site:lu.ma wealthtech roundtable India"},
    {"source_type": "community_events", "query_mode": "trusted_site", "query": "site:meetup.com financial services meetup India"},
    {"source_type": "industry_bodies", "query_mode": "trusted_site", "query": "site:cfasocietyindia.org investment event India"},
    {"source_type": "industry_bodies", "query_mode": "trusted_site", "query": "site:amfiindia.com mutual fund distributor event"},
    {"source_type": "industry_bodies", "query_mode": "trusted_site", "query": "site:nism.ac.in investor awareness webinar"},
    {"source_type": "industry_bodies", "query_mode": "trusted_site", "query": "site:ivca.in AIF summit India"},

    # Open-web intent queries
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"AIF PMS conclave India" "register"'},
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"wealth management summit India" "agenda"'},
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"mutual fund distributor conference India" "speakers"'},
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"family office summit India" "venue"'},
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"investment advisory webinar India" "registration"'},
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"financial planning seminar India" "register"'},
    {"source_type": "official_event_pages", "query_mode": "open_web_intent", "query": '"asset management conference India" "agenda"'},

    # Broad discovery queries
    {"source_type": "open_web_discovery", "query_mode": "broad_discovery", "query": "upcoming financial services events India wealth management"},
    {"source_type": "open_web_discovery", "query_mode": "broad_discovery", "query": "upcoming investment webinars India PMS AIF"},
    {"source_type": "open_web_discovery", "query_mode": "broad_discovery", "query": "financial advisory workshop India registration"},
    {"source_type": "open_web_discovery", "query_mode": "broad_discovery", "query": "wealthtech roundtable India"},
    {"source_type": "open_web_discovery", "query_mode": "broad_discovery", "query": "family office private wealth event India"},
    {"source_type": "open_web_discovery", "query_mode": "broad_discovery", "query": "mutual fund distributor conference India"},
]


def get_daily_queries(day=0):
    """Return all configured queries or a rotating subset when DAILY_QUERY_LIMIT is set."""
    if DAILY_QUERY_LIMIT is None:
        return SEARCH_SOURCE_QUERIES

    start = (day * DAILY_QUERY_LIMIT) % len(SEARCH_SOURCE_QUERIES)
    end = start + DAILY_QUERY_LIMIT

    if end <= len(SEARCH_SOURCE_QUERIES):
        return SEARCH_SOURCE_QUERIES[start:end]

    return SEARCH_SOURCE_QUERIES[start:] + SEARCH_SOURCE_QUERIES[: end - len(SEARCH_SOURCE_QUERIES)]
