#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import build_dashboard  # noqa: E402


SYNC_DIR = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Market Dashboard"
SYNC_DOWNLOADS_DIR = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Downloads/Market Dashboard"
OUTPUT_DIR = ROOT / "output" / "market_dashboard"
LOG_DIR = ROOT / "logs"
EMAIL_ENV_FILE = ROOT / "config" / "email.env"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def format_score(asset: dict) -> str:
    recommendation = asset["analysis"]["recommendation"]
    return (
        f"{recommendation['label']} | score {recommendation['score']}/100 | "
        f"confidence {recommendation['confidence']}/100 | timeframe {recommendation['timeframe']}"
    )


def render_markdown(payload: dict) -> str:
    ranked = payload["recommendations"]["ranked"]
    summary = payload["recommendations"]["summary"]

    lines = [
        "# Market Dashboard Summary",
        "",
        f"Generated: {payload['generatedAt']}",
        "",
        "## Topline",
        f"- Best setup: {summary['bestSetup']['ticker']} ({summary['bestSetup']['label']}, {summary['bestSetup']['score']}/100)",
        f"- Worst setup: {summary['worstSetup']['ticker']} ({summary['worstSetup']['label']}, {summary['worstSetup']['score']}/100)",
        f"- Best risk/reward: {summary['bestRiskReward']['ticker']} ({summary['bestRiskReward']['label']}, {summary['bestRiskReward']['score']}/100)",
        f"- Highest risk: {summary['highestRisk']['ticker']} ({summary['highestRisk']['label']}, {summary['highestRisk']['score']}/100)",
        f"- Strongest crypto: {summary['strongestCrypto']['ticker']} ({summary['strongestCrypto']['label']}, {summary['strongestCrypto']['score']}/100)",
        f"- Strongest stock: {summary['strongestStock']['ticker']} ({summary['strongestStock']['label']}, {summary['strongestStock']['score']}/100)",
        f"- Overall market tone: {summary['overallMarketTone']}",
        "",
        "## Ranked Watchlist",
    ]

    for index, item in enumerate(ranked, start=1):
        asset = next(asset for asset in payload["assets"] if asset["ticker"] == item["ticker"])
        analysis = asset["analysis"]
        lines.extend(
            [
                "",
                f"### {index}. {asset['name']} ({asset['ticker']})",
                f"- Type: {asset['type']}",
                f"- Price: {asset['currentPrice'] if asset['currentPrice'] is not None else 'Unavailable'}",
                f"- Recommendation: {format_score(asset)}",
                f"- Trend directions: 1D {analysis['trendDirections']['1D']}, 1W {analysis['trendDirections']['1W']}, 1M {analysis['trendDirections']['1M']}",
                f"- Momentum: {analysis['momentumSummary']}",
                f"- Support / resistance: {analysis['supportZone']} / {analysis['resistanceZone']}",
                f"- Volatility: {analysis['volatilityLevel']}",
                f"- Breakout / breakdown: {analysis['breakoutBreakdownRisk']} - {analysis['breakoutBreakdownDetail']}",
                f"- News alignment: {analysis['priceNewsAlignment']}",
                f"- Summary: {asset['summary']}",
                "- Key reasons:",
            ]
        )
        lines.extend(f"  - {reason}" for reason in item["keyReasons"])
        lines.append("- Risks:")
        lines.extend(f"  - {risk}" for risk in item["risks"])
        lines.append("- Strengthens:")
        lines.extend(f"  - {point}" for point in item["strengthen"])
        lines.append("- Weakens:")
        lines.extend(f"  - {point}" for point in item["weaken"])

    return "\n".join(lines) + "\n"


def render_text(payload: dict) -> str:
    ranked = payload["recommendations"]["ranked"]
    summary = payload["recommendations"]["summary"]
    lines = [
        "MARKET DASHBOARD SUMMARY",
        f"Generated: {payload['generatedAt']}",
        "",
        "TOPLINE",
        f"Best setup: {summary['bestSetup']['ticker']} ({summary['bestSetup']['label']}, {summary['bestSetup']['score']}/100)",
        f"Worst setup: {summary['worstSetup']['ticker']} ({summary['worstSetup']['label']}, {summary['worstSetup']['score']}/100)",
        f"Best risk/reward: {summary['bestRiskReward']['ticker']} ({summary['bestRiskReward']['label']}, {summary['bestRiskReward']['score']}/100)",
        f"Highest risk: {summary['highestRisk']['ticker']} ({summary['highestRisk']['label']}, {summary['highestRisk']['score']}/100)",
        f"Strongest crypto: {summary['strongestCrypto']['ticker']} ({summary['strongestCrypto']['label']}, {summary['strongestCrypto']['score']}/100)",
        f"Strongest stock: {summary['strongestStock']['ticker']} ({summary['strongestStock']['label']}, {summary['strongestStock']['score']}/100)",
        f"Overall market tone: {summary['overallMarketTone']}",
        "",
        "RANKED WATCHLIST",
    ]

    for index, item in enumerate(ranked, start=1):
        asset = next(asset for asset in payload["assets"] if asset["ticker"] == item["ticker"])
        analysis = asset["analysis"]
        lines.extend(
            [
                "",
                f"{index}. {asset['name']} ({asset['ticker']})",
                f"   {format_score(asset)}",
                f"   Trend: 1D {analysis['trendDirections']['1D']} | 1W {analysis['trendDirections']['1W']} | 1M {analysis['trendDirections']['1M']}",
                f"   Momentum: {analysis['momentumSummary']}",
                f"   Support/Resistance: {analysis['supportZone']} / {analysis['resistanceZone']}",
                f"   Volatility: {analysis['volatilityLevel']}",
                f"   Summary: {asset['summary']}",
                f"   Reasons: {'; '.join(item['keyReasons'])}",
                f"   Risks: {'; '.join(item['risks'])}",
            ]
        )

    return "\n".join(lines) + "\n"


def maybe_send_email(subject: str, text_body: str, markdown_body: str, attachment_paths: list[Path]) -> str:
    load_env_file(EMAIL_ENV_FILE)
    required = [
        "MARKET_SUMMARY_EMAIL_TO",
        "MARKET_SUMMARY_EMAIL_FROM",
        "MARKET_SUMMARY_SMTP_HOST",
        "MARKET_SUMMARY_SMTP_PORT",
        "MARKET_SUMMARY_SMTP_USERNAME",
        "MARKET_SUMMARY_SMTP_PASSWORD",
    ]
    missing = [key for key in required if not os.environ.get(key)]

    if missing:
        return f"Email skipped. Missing config: {', '.join(missing)}"

    message = EmailMessage()
    message["To"] = os.environ["MARKET_SUMMARY_EMAIL_TO"]
    message["From"] = os.environ["MARKET_SUMMARY_EMAIL_FROM"]
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(f"<pre>{markdown_body}</pre>", subtype="html")

    for path in attachment_paths:
        data = path.read_bytes()
        maintype = "text"
        subtype = "markdown" if path.suffix == ".md" else "plain"
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    port = int(os.environ["MARKET_SUMMARY_SMTP_PORT"])
    host = os.environ["MARKET_SUMMARY_SMTP_HOST"]
    username = os.environ["MARKET_SUMMARY_SMTP_USERNAME"]
    password = os.environ["MARKET_SUMMARY_SMTP_PASSWORD"]
    use_ssl = os.environ.get("MARKET_SUMMARY_SMTP_SSL", "true").lower() == "true"

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(message)

    return f"Email sent to {os.environ['MARKET_SUMMARY_EMAIL_TO']}"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    payload = build_dashboard()
    markdown = render_markdown(payload)
    text = render_text(payload)

    dashboard_json = OUTPUT_DIR / "latest_dashboard.json"
    local_md = ROOT / "latest_summary.md"
    local_txt = ROOT / "latest_summary.txt"
    synced_md = SYNC_DIR / "latest_summary.md"
    synced_txt = SYNC_DIR / "latest_summary.txt"
    downloads_md = SYNC_DOWNLOADS_DIR / "latest_summary.md"
    downloads_txt = SYNC_DOWNLOADS_DIR / "latest_summary.txt"

    dashboard_json.write_text(json.dumps(payload, indent=2) + "\n")
    local_md.write_text(markdown)
    local_txt.write_text(text)
    synced_md.write_text(markdown)
    synced_txt.write_text(text)
    downloads_md.write_text(markdown)
    downloads_txt.write_text(text)

    email_status = maybe_send_email(
        subject=f"Market Dashboard Summary - {payload['generatedAt']}",
        text_body=text,
        markdown_body=markdown,
        attachment_paths=[synced_md, synced_txt],
    )

    print(f"Wrote dashboard snapshot to {dashboard_json}")
    print(f"Wrote local markdown summary to {local_md}")
    print(f"Wrote local text summary to {local_txt}")
    print(f"Wrote synced markdown summary to {synced_md}")
    print(f"Wrote synced text summary to {synced_txt}")
    print(f"Wrote iCloud Downloads markdown summary to {downloads_md}")
    print(f"Wrote iCloud Downloads text summary to {downloads_txt}")
    print(email_status)


if __name__ == "__main__":
    main()
