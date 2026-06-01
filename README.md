# Financial Services Event Intelligence Monitor

## 1. Overview
The **Financial Services Event Intelligence Monitor** is an automated intelligence pipeline designed to discover, extract, and analyze upcoming events (Conferences, Summits, Webinars, Workshops, Meetups) within India's Banking, Financial Services, and Insurance (BFSI) ecosystem. 

**Key Features:**
- **Automated Discovery:** Queries Google Search (via Serper API) daily to find relevant LinkedIn posts about financial events published in the last 24 hours.
- **Intelligent Deduplication:** Maintains a local history to ensure you never receive the same event twice. Events are deduplicated by event name, dates, and type, preserving the most complete version.
- **AI-Powered Enrichment:** Leverages OpenRouter to automatically extract structured event intelligence (Name, Dates, Location, Organiser, Audience, Link). Includes a robust heuristic/regex-based fallback layer.
- **Premium Reporting:** Generates a visually appealing, responsive HTML "Event Intelligence Dashboard" email detailing the daily upcoming events grouped by category.
- **Cloud-Ready:** Designed to run seamlessly as a scheduled GitHub Action.

**Target Users:**
Professionals in AMC, AIF, PMS, Wealth Management, and FinTech who need a curated, daily digest of industry events, summits, and webinars without manually scrolling through LinkedIn.

---

## 2. Architecture Flow
The system follows a linear, modular **Extract, Transform, Load (ETL)** pipeline pattern, now heavily focused on treating *events* as the primary entity.

1. **Fetch (`scraper.py`)**: Uses Serper API to query Google for recent LinkedIn posts matching specific event and BFSI keywords. Applies semantic filtering to keep high-signal posts.
2. **Enrich (`enricher.py`)**: Passes the raw text to OpenRouter for structural event extraction, or falls back to rule-based regex to pull event details. Normalizes dates, locations, and extracts external registration links.
3. **Deduplicate (`deduplicator.py`)**: Checks the extracted event entities against a persistent JSON database. If an event is already known, it updates the record if the new post provides a *more complete* payload.
4. **Report (`reporter.py`)**: Compiles the enriched, unique event data into an HTML template, categorized by event type, and dispatches it via SMTP.
5. **Orchestrate (`main.py`)**: Ties the modules together and manages execution flow.

---

## 3. Supported Categories & Sectors

**Supported Event Categories:**
- Conferences
- Summits
- Webinars
- Workshops
- Meetups

**Supported Financial Sectors:**
- AMC (Asset Management Companies)
- AIF (Alternative Investment Funds)
- PMS (Portfolio Management Services)
- Wealth Management
- Financial Advisory
- Investment Platforms
- WealthTech
- FinTech (Investment/Wealth related)

---

## 4. Setup & Installation

### Prerequisites
- Python 3.10+
- A [Serper API](https://serper.dev/) Account
- An [OpenRouter](https://openrouter.ai/) API key
- A Gmail Account with an "App Password"

### Step-by-Step Setup
1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   SERPER_API_KEY=your_serper_key_here
   OPENROUTER_API_KEY=your_openrouter_key_here
   OPENROUTER_MODELS=openai/gpt-oss-120b:free,deepseek/deepseek-v4-flash:free,z-ai/glm-4.5-air:free,mistralai/mistral-7b-instruct:free,meta-llama/llama-3-8b-instruct:free
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   REPORT_TO=recipient1@example.com, recipient2@example.com
   REPORT_FROM=your_email@gmail.com
   ```

---

## 5. Usage

### Diagnostics
Verify your environment and API keys:
```bash
python test_pipeline.py
```

### Running Locally
To run a single execution of the pipeline immediately:
```bash
python main.py
```

### Running as a Local Service
To run the script continuously, triggering daily at the time specified in `config.py`:
```bash
python main.py --schedule
```

### Cloud Scheduling (GitHub Actions)
The repository includes a GitHub Action (`.github/workflows/daily_report.yml`) that automatically runs the pipeline on a schedule.
1. Push the code to GitHub.
2. Add your `.env` variables to **GitHub Repository Settings > Secrets and variables > Actions**.

---

## 6. Structured Event Intelligence
Each event is parsed into a structured payload containing:
- **Event Name**: Extracted heuristically or via LLM.
- **Event Type**: Normalized to core categories.
- **Event Dates**: Normalized to standard formats via `dateparser`.
- **Location**: Extracted cities or flagged as "Online/Virtual".
- **Organiser**: Extracted host entities.
- **Target Audience**: Who the event is aimed at.
- **Official Link**: Extracted outbound URLs (e.g. Eventbrite, Hubilo, Luma).
- **Description**: Concise factual summary.

---

## 7. HTML Event Digest
The pipeline generates a beautifully formatted HTML report summarizing market sentiment (total events by type) and rendering individual event cards. Cards include interactive badges for virtual/in-person status, source domain metadata, and a direct Call-To-Action (CTA) registration button for valid outbound links.
