#!/usr/bin/env python3
"""
Simple Geopolitical News Report

How to run:
1. Open a terminal in this project folder.
2. Run: python3 scripts/simple_geopolitical_report.py
3. The report will print in the terminal and also be saved to:
   reports/simple_geopolitical_report.txt

Notes:
- This script uses free RSS feeds, so no API key is required.
- It focuses on major geopolitical stories such as wars, trade disputes,
  military developments, energy disruptions, and major elections.
"""

from __future__ import annotations

import email.utils
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "reports" / "simple_geopolitical_report.txt"
MAX_ITEMS_PER_FEED = 15
MAX_STORIES = 8

FEEDS = [
    {"name": "BBC", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "DW", "url": "https://rss.dw.com/rdf/rss-en-world"},
    {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
]

KEYWORDS = {
    "war",
    "conflict",
    "military",
    "troops",
    "missile",
    "strike",
    "sanctions",
    "trade",
    "tariff",
    "oil",
    "gas",
    "energy",
    "election",
    "summit",
    "diplomacy",
    "china",
    "taiwan",
    "russia",
    "ukraine",
    "israel",
    "gaza",
    "iran",
    "nato",
}

COUNTRY_KEYWORDS = {
    "United States": {"us", "u.s", "american", "washington", "trump"},
    "China": {"china", "beijing"},
    "Taiwan": {"taiwan", "taipei"},
    "Russia": {"russia", "moscow", "putin"},
    "Ukraine": {"ukraine", "kyiv", "zelensky"},
    "Israel": {"israel", "israeli"},
    "Palestinian Territories": {"gaza", "palestinian", "palestinians", "west bank"},
    "Iran": {"iran", "tehran", "hormuz"},
    "European Union": {"eu", "european", "brussels"},
    "United Kingdom": {"uk", "u.k", "britain", "british"},
    "India": {"india", "indian"},
    "Pakistan": {"pakistan", "pakistani"},
}

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "have",
    "has",
    "will",
    "into",
    "amid",
    "after",
    "about",
    "what",
    "world",
    "news",
}


@dataclass
class Story:
    source: str
    title: str
    link: str
    summary: str
    published: datetime


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z]{3,}", text.lower())
        if token not in STOP_WORDS
    ]


def get_child_text(node: ET.Element, *names: str) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def parse_feed(feed: dict[str, str]) -> list[Story]:
    root = ET.fromstring(fetch_text(feed["url"]))
    stories: list[Story] = []

    for item in root.findall(".//item")[:MAX_ITEMS_PER_FEED]:
        title = clean_html(get_child_text(item, "title"))
        link = clean_html(get_child_text(item, "link"))
        description = clean_html(get_child_text(item, "description"))
        published = parse_date(get_child_text(item, "pubDate", "published", "updated"))

        tokens = set(tokenize(f"{title} {description}"))
        if not title or not link or not (tokens & KEYWORDS):
            continue

        stories.append(
            Story(
                source=feed["name"],
                title=title,
                link=link,
                summary=description,
                published=published,
            )
        )

    return stories


def classify_group(story: Story) -> str:
    text = f"{story.title} {story.summary}".lower()
    if any(word in text for word in ["iran", "hormuz", "nuclear"]):
        return "Iran and Gulf tensions"
    if any(word in text for word in ["gaza", "west bank", "hamas", "palestinian"]):
        return "Israel-Palestine conflict"
    if any(word in text for word in ["ukraine", "kyiv", "zelensky"]):
        return "Russia-Ukraine war"
    if any(word in text for word in ["china", "taiwan", "beijing", "taipei"]):
        return "China-Taiwan and great-power competition"
    if any(word in text for word in ["trade", "tariff", "sanctions"]):
        return "Trade conflict and sanctions"
    if any(word in text for word in ["oil", "gas", "energy"]):
        return "Energy disruption"
    if any(word in text for word in ["election", "vote", "campaign"]):
        return "Election with global consequences"
    return story.title


def detect_countries(text: str) -> list[str]:
    lower_text = text.lower()
    found: list[str] = []

    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            found.append(country)

    return found[:5] or ["Not clear from headline alone"]


def build_summary(group_name: str, stories: list[Story]) -> str:
    lead = stories[0]
    supporting = len({story.source for story in stories})
    sentence_one = f"{lead.title}."
    sentence_two = f"This development appeared across {supporting} major source{'s' if supporting != 1 else ''}, suggesting it is being treated as a meaningful international story."

    if "trade" in group_name.lower() or "sanctions" in group_name.lower():
        sentence_three = "The reporting points to possible knock-on effects for supply chains, industrial policy, and cross-border commerce."
    elif "energy" in group_name.lower() or "gulf" in group_name.lower():
        sentence_three = "The reporting suggests possible effects on oil flows, shipping routes, and broader market risk sentiment."
    elif "election" in group_name.lower():
        sentence_three = "The story could matter beyond domestic politics if the outcome changes foreign policy, alliances, or trade policy."
    else:
        sentence_three = "The story matters because it may influence diplomacy, military planning, or regional stability."

    return " ".join([sentence_one, sentence_two, sentence_three])


def build_why_it_matters(group_name: str, countries: list[str]) -> str:
    country_text = ", ".join(countries[:3])

    if "trade" in group_name.lower() or "sanctions" in group_name.lower():
        return f"This could reshape trade expectations and policy risk for countries connected to {country_text}."
    if "energy" in group_name.lower() or "gulf" in group_name.lower():
        return f"This could affect energy prices, shipping security, and inflation expectations tied to {country_text}."
    if "war" in group_name.lower() or "conflict" in group_name.lower():
        return f"This could raise geopolitical risk, affect defense planning, and shift diplomatic pressure involving {country_text}."
    if "china-taiwan" in group_name.lower() or "great-power" in group_name.lower():
        return f"This could influence military signaling, technology supply chains, and broader strategic competition involving {country_text}."
    return f"This could affect regional stability and policy decisions involving {country_text}."


def build_report(stories: list[Story]) -> str:
    grouped: dict[str, list[Story]] = defaultdict(list)
    for story in stories:
        grouped[classify_group(story)].append(story)

    ranked_groups = sorted(
        grouped.items(),
        key=lambda item: (
            len({story.source for story in item[1]}),
            max(story.published for story in item[1]),
        ),
        reverse=True,
    )[:MAX_STORIES]
    ranked_groups = [
        item
        for item in ranked_groups
        if len({story.source for story in item[1]}) >= 2
        or item[0] in {
            "Iran and Gulf tensions",
            "Israel-Palestine conflict",
            "Russia-Ukraine war",
            "China-Taiwan and great-power competition",
            "Trade conflict and sanctions",
            "Energy disruption",
            "Election with global consequences",
        }
    ]

    lines = [
        "GEOPOLITICAL NEWS REPORT",
        f"Generated: {datetime.now().astimezone().strftime('%Y-%m-%d %I:%M %p %Z')}",
        "",
    ]

    if not ranked_groups:
        lines.append("No major geopolitical stories were found in the current scan.")
        return "\n".join(lines) + "\n"

    for index, (group_name, group_stories) in enumerate(ranked_groups, start=1):
        lead_story = sorted(group_stories, key=lambda story: story.published, reverse=True)[0]
        countries = detect_countries(f"{lead_story.title} {lead_story.summary}")
        lines.extend(
            [
                f"{index}. Headline: {group_name}",
                f"   Summary: {build_summary(group_name, group_stories)}",
                f"   Countries involved: {', '.join(countries)}",
                f"   Why it matters: {build_why_it_matters(group_name, countries)}",
                f"   Source link: {lead_story.link}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_stories: list[Story] = []
    for feed in FEEDS:
        try:
            all_stories.extend(parse_feed(feed))
        except Exception as exc:
            print(f"Warning: could not read {feed['name']} feed: {exc}")

    report = build_report(all_stories)
    print(report, end="")
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Saved report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
