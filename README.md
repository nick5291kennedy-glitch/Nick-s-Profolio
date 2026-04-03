# Market Intelligence Dashboard

A clean local dashboard for 8 assets across crypto and stocks:

- ONDO
- LINK
- BTC
- ETH
- CCJ
- ACHR
- ASTS
- UNH

It combines:

- latest available price data
- daily, weekly, and monthly performance
- 1D, 1W, and 1M chart views
- recent headlines
- bullish and bearish signal lists
- a short neutral summary for each asset
- a Recommendations tab with ranked setups and score breakdowns

## Data sources

- Crypto prices and chart history: Yahoo Finance chart endpoint
- Stock prices and chart history: Yahoo Finance chart endpoint
- Recent news: Google News RSS search results

All of these are wired through the local Python server so the browser only needs to call one endpoint: `/api/dashboard`.

## Run locally

```bash
cd "/Users/nicholaskennedy/Documents/New project"
python3 server.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Installable app versions

### PWA

The dashboard can now be installed as a Progressive Web App.

Files:

- `manifest.webmanifest`
- `service-worker.js`
- `icons/icon-180.png`
- `icons/icon-192.png`
- `icons/icon-512.png`
- `icons/icon-maskable-512.png`

How to install:

- On iPhone: open the dashboard URL in Safari, tap `Share`, then tap `Add to Home Screen`
- On Mac in Chrome or Edge: open the dashboard URL and use the install button in the address bar

### macOS app

A Mac app launcher is included and can be rebuilt anytime.

Build script:

- `scripts/build_mac_app.sh`

Generated app:

- `dist/Market Intelligence Dashboard.app`

Downloadable zip:

- `dist/Market-Intelligence-Dashboard-mac.zip`

The Mac app launches the local dashboard server if needed and opens the dashboard automatically.

## Notes

- No API keys are required for the current setup.
- Dashboard responses are cached in memory for 5 minutes to avoid unnecessary API calls.
- If one upstream source fails temporarily, the dashboard still tries to render the rest of the assets.
- Use the Dashboard tab for quick scanning and the Recommendations tab for ranked setup review.
- Click any asset card or recommendation card to open the detailed technical view.

## Daily refresh

The project is set up to generate a fresh dashboard snapshot and summary every day at `1:00 PM` local time using `launchd`.

Installed job:

- `com.marketdashboard.refresh`

Job file:

- `launchd/com.marketdashboard.refresh.plist`

Refresh runner:

- `scripts/run_market_refresh.sh`

Summary generator:

- `scripts/generate_market_summary.py`

The daily refresh writes:

- local markdown summary: `latest_summary.md`
- local text summary: `latest_summary.txt`
- dashboard snapshot JSON: `output/market_dashboard/latest_dashboard.json`
- synced markdown summary: `~/Library/Mobile Documents/com~apple~CloudDocs/Market Dashboard/latest_summary.md`
- synced text summary: `~/Library/Mobile Documents/com~apple~CloudDocs/Market Dashboard/latest_summary.txt`
- iCloud Downloads markdown summary: `~/Library/Mobile Documents/com~apple~CloudDocs/Downloads/Market Dashboard/latest_summary.md`
- iCloud Downloads text summary: `~/Library/Mobile Documents/com~apple~CloudDocs/Downloads/Market Dashboard/latest_summary.txt`

You can run the workflow manually anytime with:

```bash
cd "/Users/nicholaskennedy/Documents/New project"
./scripts/run_market_refresh.sh
```

## Email setup

Email delivery is implemented but optional. It will send after each run only when you create:

- `config/email.env`

Start from:

- `config/email.env.example`

Required variables:

- `MARKET_SUMMARY_EMAIL_TO`
- `MARKET_SUMMARY_EMAIL_FROM`
- `MARKET_SUMMARY_SMTP_HOST`
- `MARKET_SUMMARY_SMTP_PORT`
- `MARKET_SUMMARY_SMTP_USERNAME`
- `MARKET_SUMMARY_SMTP_PASSWORD`

Optional:

- `MARKET_SUMMARY_SMTP_SSL=true`

## Files

- `server.py`: local API server and market/news aggregation
- `index.html`: dashboard markup
- `styles.css`: dashboard styling
- `game.js`: client-side rendering and chart drawing
