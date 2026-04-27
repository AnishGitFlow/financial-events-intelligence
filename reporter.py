"""
reporter.py - Premium Intelligence Report Generator (v2)
Generates high-end HTML reports and sends via SMTP.
"""
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import Counter, defaultdict
from urllib.parse import urlparse

from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    REPORT_TO, REPORT_FROM,
    HIGH_PRIORITY_SOURCES, MEDIUM_PRIORITY_SOURCES,
)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "data", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── Design Tokens (Professional BFSI Palette) ──────────────────────────────────
COLORS = {
    "primary":   "#0f172a", # Deep Navy
    "accent":    "#1d4ed8", # Professional Blue
    "success":   "#059669", # Emerald
    "warning":   "#d97706", # Amber
    "danger":    "#dc2626", # Red
    "background":"#f8fafc", # Slate background
    "card":      "#ffffff",
    "text_main": "#1e293b",
    "text_muted":"#64748b",
}

CAT_COLORS = {
    "Conference":               "#1d4ed8",
    "Summit":                   "#7c3aed",
    "Webinar":                  "#059669",
    "Workshop":                 "#d97706",
    "Meetup":                   "#db2777",
    "Other":                    "#475569",
}

def _get_cat_color(cat: str) -> str:
    return CAT_COLORS.get(cat, "#475569")


def _get_priority(company_type: str) -> str:
    """Return 'high', 'medium', or 'normal' based on company_type field."""
    if company_type == "High Priority":
        return "high"
    if company_type == "Medium Priority":
        return "medium"
    return "normal"


def _priority_badge(company_type: str) -> str:
    """Return an HTML priority badge or empty string."""
    if company_type == "High Priority":
        return _badge("🔴 High Priority", "#dc2626")
    if company_type == "Medium Priority":
        return _badge("🟡 Medium Priority", "#d97706")
    return ""


def _clean_author_name(name: str) -> str:
    """
    Strip hashtag-heavy content from author names.
    LinkedIn og:titles sometimes contain '#tag1 #tag2 | Real Name'.
    We extract the real name from after the last '|' separator if present,
    otherwise strip all leading hashtag tokens.
    """
    if not name:
        return "Unknown Source"
    # If the name contains ' | ', take the part after the last pipe
    if " | " in name:
        name = name.split(" | ")[-1].strip()
    # Strip any remaining leading hashtag tokens
    tokens = name.split()
    cleaned = [t for t in tokens if not t.startswith("#")]
    result = " ".join(cleaned).strip()
    return result if result else "Unknown Source"

# ── Report Logic ────────────────────────────────────────────────────────────────

def generate_report(posts: list[dict]) -> dict:
    run_time = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at":  run_time,
        "total_posts":   len(posts),
        "posts":         posts,
    }

def _badge(text: str, bg: str) -> str:
    return (f'<span style="display:inline-block;padding:3px 10px;border-radius:6px;'
            f'font-size:11px;font-weight:700;color:#ffffff;background:{bg};'
            f'text-transform:uppercase;letter-spacing:0.5px;">{text}</span>')

def _build_html(report: dict) -> str:
    posts    = report["posts"]
    total    = len(posts)
    run_date = datetime.now(timezone.utc).strftime("%d %b %Y | %H:%M UTC")
    
    # Stats
    cat_counts  = Counter(p.get("event_type", "Other") for p in posts)
    conferences = sum(1 for p in posts if p.get("event_type") == "Conference")
    webinars    = sum(1 for p in posts if p.get("event_type") == "Webinar")
    summits     = sum(1 for p in posts if p.get("event_type") == "Summit")

    # Category Table Rows
    cat_rows = ""
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        cat_rows += f"""
        <tr>
            <td style="padding:10px 0; border-bottom:1px solid #e2e8f0; color:{COLORS['text_main']}; font-weight:500;">{cat}</td>
            <td style="padding:10px 0; border-bottom:1px solid #e2e8f0; text-align:right; font-weight:700; color:{COLORS['primary']};">{count}</td>
        </tr>"""

    # Group posts by event type
    grouped_posts = defaultdict(list)
    for p in posts:
        grouped_posts[p.get("event_type", "Other")].append(p)

    # Post Cards
    post_cards = ""
    for category in ["Conference", "Summit", "Webinar", "Workshop", "Meetup", "Other"]:
        cat_posts = grouped_posts.get(category, [])
        if not cat_posts:
            continue
            
        post_cards += f'<h3 style="margin: 24px 0 16px; color:{COLORS["primary"]}; border-bottom:2px solid {COLORS["accent"]}; display:inline-block; padding-bottom:4px;">{category}s</h3>'
        
        for p in cat_posts:
            color = _get_cat_color(category)
            official_link = p.get("official_link")
            has_official = official_link and official_link != "Not specified"
            
            source_domain = ""
            if has_official:
                try:
                    domain = urlparse(official_link).netloc.replace("www.", "")
                    source_domain = f' | <b>Domain:</b> {domain}'
                except Exception:
                    pass

            cta_button = f'<a href="{official_link}" style="display:inline-block; padding:10px 20px; background:{COLORS["accent"]}; color:#ffffff; text-decoration:none; border-radius:6px; font-weight:600; font-size:14px;">Register Now &rarr;</a>' if has_official else f'<a href="{p.get("post_url")}" style="color:{COLORS["accent"]}; text-decoration:none; font-weight:600; font-size:14px;">View LinkedIn Post &rarr;</a>'
            
            loc = p.get('location', 'Not specified')
            is_virtual = loc.lower() == "online/virtual"
            loc_badge = _badge("💻 Virtual", COLORS["success"]) if is_virtual else _badge(f"📍 {loc}", COLORS["warning"])
            
            post_cards += f"""
            <div style="background:{COLORS['card']}; border-radius:12px; padding:24px; margin-bottom:20px; border:1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
                <div style="margin-bottom:16px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <div>{_badge(category, color)} <span style="margin-left:8px;">{loc_badge}</span></div>
                        <span style="font-size:12px; color:{COLORS['text_muted']}; font-weight:600;">🗓️ {p.get('event_dates', 'Dates Not specified')}</span>
                    </div>
                    <h3 style="margin:0; font-size:18px; color:{COLORS['primary']}; font-weight:700; line-height:1.3; padding-top:8px;">
                        {p.get('event_name', 'Event Name Not Specified')}
                    </h3>
                    <div style="font-size:13px; color:{COLORS['text_muted']}; margin-top:8px;">
                        <b>Organiser:</b> {p.get('organiser', 'Not specified')} | <b>Audience:</b> {p.get('target_audience', 'Not specified')}
                    </div>
                    <div style="font-size:13px; color:{COLORS['text_muted']}; margin-top:4px;">
                        <b>Source:</b> {_clean_author_name(p.get('source_name', ''))}{source_domain}
                    </div>
                </div>
                
                <div style="background:#f1f5f9; padding:16px; border-radius:8px; border-left:4px solid {color}; margin-bottom:16px;">
                    <p style="margin:0; font-size:14px; color:{COLORS['text_main']}; line-height:1.6;">
                        {p.get('description', 'No description available.')}
                    </p>
                </div>
    
                <div style="border-top:1px solid #f1f5f9; padding-top:16px; text-align:right;">
                    {cta_button}
                </div>
            </div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0; padding:0; background-color:{COLORS['background']}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
        
        <!-- HEADER SECTION -->
        <div style="background-color:{COLORS['primary']}; padding:48px 24px; text-align:center; color:#ffffff;">
            <p style="text-transform:uppercase; letter-spacing:2px; font-size:11px; margin-bottom:8px; opacity:0.8;">Daily Intelligence</p>
            <h1 style="margin:0; font-size:28px; font-weight:800; letter-spacing:-0.5px;">Financial Events Monitor</h1>
            <p style="margin-top:12px; font-size:14px; opacity:0.7;">{run_date}</p>
            
            <div style="display:inline-flex; margin-top:32px; gap:20px; text-align:center;">
                <div style="padding:0 20px; border-right:1px solid rgba(255,255,255,0.2);">
                    <div style="font-size:24px; font-weight:800;">{total}</div>
                    <div style="font-size:10px; text-transform:uppercase; opacity:0.6;">Total Events</div>
                </div>
                <div style="padding:0 20px; border-right:1px solid rgba(255,255,255,0.2);">
                    <div style="font-size:24px; font-weight:800; color:#60a5fa;">{conferences}</div>
                    <div style="font-size:10px; text-transform:uppercase; opacity:0.6;">Conferences</div>
                </div>
                <div style="padding:0 20px; border-right:1px solid rgba(255,255,255,0.2);">
                    <div style="font-size:24px; font-weight:800; color:#059669;">{webinars}</div>
                    <div style="font-size:10px; text-transform:uppercase; opacity:0.6;">Webinars</div>
                </div>
                <div style="padding:0 20px;">
                    <div style="font-size:24px; font-weight:800; color:#7c3aed;">{summits}</div>
                    <div style="font-size:10px; text-transform:uppercase; opacity:0.6;">Summits</div>
                </div>
            </div>
        </div>

        <!-- MAIN CONTENT -->
        <div style="max-width:600px; margin: -20px auto 40px; padding:0 20px;">
            
            <!-- SUMMARY TABLE CARD -->
            <div style="background:{COLORS['card']}; border-radius:12px; padding:24px; margin-bottom:30px; border:1px solid #e2e8f0; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);">
                <h2 style="margin:0 0 16px; font-size:16px; color:{COLORS['primary']}; text-transform:uppercase; letter-spacing:1px;">Event Summary</h2>
                <table style="width:100%; border-collapse:collapse;">
                    {cat_rows}
                </table>
            </div>

            <!-- INDIVIDUAL POSTS -->
            <h2 style="font-size:14px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:1px; margin-bottom:16px; padding-left:4px;">Detailed Insights</h2>
            {post_cards}

            <!-- FOOTER -->
            <div style="text-align:center; padding:40px 0; border-top:1px solid #e2e8f0; margin-top:20px;">
                <p style="font-size:12px; color:{COLORS['text_muted']}; line-height:1.5;">
                    This is an automated intelligence report generated by the <br>
                    <b>Financial Services Event Intelligence Monitor</b>.<br>
                    Unsubscribe or Manage Alerts in your config.
                </p>
                <div style="margin-top:16px;">
                    <span style="font-size:10px; background:#e2e8f0; padding:4px 8px; border-radius:4px; color:{COLORS['text_muted']};">Powered by Serper API & Gemini</span>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def save_report(report: dict) -> tuple[str, dict]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORTS_DIR, f"report_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    html_content = _build_html(report)
    html_path = os.path.join(REPORTS_DIR, f"report_{stamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return html_content, report

def send_email_report(html: str, json_report: dict) -> None:
    if not all([REPORT_TO, SMTP_USER, SMTP_PASSWORD]):
        print("[Reporter] Email config missing.")
        return

    recipients = [r.strip() for r in REPORT_TO.split(",") if r.strip()]
    total = json_report.get("total_posts", 0)
    run_date = datetime.now(timezone.utc).strftime("%d %b")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"📅 Event Intelligence: {total} Events Tracked ({run_date})"
    msg["From"] = REPORT_FROM
    msg["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("Please view the HTML version for the full report.", "plain"))
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(REPORT_FROM, recipients, msg.as_string())
        print(f"[Reporter] Premium report sent to {len(recipients)} recipients.")
    except Exception as e:
        print(f"[Reporter] Error: {e}")
