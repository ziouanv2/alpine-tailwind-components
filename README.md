# Web Research Collector

This project provides an asynchronous command-line utility that reads keywords, queries the Google Custom Search JSON API, visits selected results with Playwright, scrolls the pages to trigger lazy loading, extracts metadata, and stores the findings in JSONL or CSV.

## Features

- Configurable via YAML and environment variables
- Uses official search APIs (Google Custom Search by default)
- Respects `robots.txt`, crawl delays, and adds random jitter to per-site delays
- Headless Chromium browsing with Playwright and incremental scrolling
- Extracts page title, final URL, HTTP status, meta description, first H1, visible word count, and capture timestamp
- Structured JSON logging with per-keyword request IDs
- Supports optional allowed/blocklisted domains and a static proxy configuration
- Outputs per-keyword JSONL files or a consolidated CSV file

## Prerequisites

1. Python 3.11+
2. Google Custom Search API key and Custom Search Engine ID (CX)
3. Playwright browsers (install via `playwright install` after dependencies)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # populate GOOGLE_API_KEY and GOOGLE_CX
```

## Configuration

Settings live in `configs/app.yml`. Environment variables override credentials:

- `GOOGLE_API_KEY`
- `GOOGLE_CX`
- (Optional) `BING_SUBSCRIPTION_KEY` if switching providers

CLI arguments override YAML entries. Example config snippet:

```yaml
api:
  provider: google
search:
  input_file: keywords.txt
  max_results_per_keyword: 5
  per_site_delay: 5
  global_rate_limit_qps: 1
  user_agent: ResearchCollector/1.0 (+https://example.com/contact)
```

## Usage

Example keyword file `keywords.txt` is provided with one query per line.

Run the collector:

```bash
python -m app.main \
  --config configs/app.yml \
  --input keywords.txt \
  --max-per-keyword 20 \
  --output results.jsonl \
  --provider google
```

Additional helpful flags:

- `--output-format csv` for a consolidated CSV file
- `--allowed-domains example.com another.org`
- `--per-site-delay 10` to tune crawl delays
- `--global-rate 0.5` to cap query rate

## Output

- JSONL: default, stored in `outputs/YYYY-MM-DD/<keyword>.jsonl`
- CSV: single file (path controlled by `--output`)

Each record contains search context and extracted page metadata.

## Testing

Run the unit tests:

```bash
pytest
```

## Compliance Notes

- The crawler checks `robots.txt` before visiting a page and obeys crawl-delay directives when provided.
- The user agent string is configurable and should identify your organization with contact details.
- The application only uses official search APIs. Respect the provider's rate limits, quotas, and terms of service.
- A single optional outbound proxy can be configured; rotation or evasion behaviour is deliberately not implemented.
