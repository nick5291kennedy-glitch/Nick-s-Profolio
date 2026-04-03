#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
BRIEFINGS_DIR = ROOT / "briefings"
REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "logs"
JSON_OUTPUT_PATH = BRIEFINGS_DIR / "latest.json"
LATEST_MARKDOWN_PATH = REPORTS_DIR / "latest.md"
MAX_ITEMS_PER_FEED = 18
MAX_STORIES = 10

FEEDS = [
    {
        "name": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "base_region": "Global",
    },
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "base_region": "Global",
    },
    {
        "name": "DW",
        "url": "https://rss.dw.com/rdf/rss-en-world",
        "base_region": "Europe",
    },
    {
        "name": "France 24",
        "url": "https://www.france24.com/en/rss",
        "base_region": "Europe",
    },
    {
        "name": "NPR",
        "url": "https://feeds.npr.org/1004/rss.xml",
        "base_region": "Americas",
    },
    {
        "name": "The Guardian",
        "url": "https://www.theguardian.com/world/rss",
        "base_region": "Global",
    },
]

COUNTRY_RULES = {
    "United States": {"us", "u.s", "america", "american", "washington", "trump"},
    "China": {"china", "chinese", "beijing"},
    "Taiwan": {"taiwan", "taipei"},
    "Russia": {"russia", "russian", "moscow", "putin"},
    "Ukraine": {"ukraine", "ukrainian", "kyiv", "zelensky"},
    "Israel": {"israel", "israeli"},
    "Palestinian Territories": {"gaza", "palestinian", "palestinians", "rafah", "west", "bank"},
    "Iran": {"iran", "iranian", "tehran", "hormuz"},
    "United Kingdom": {"uk", "u.k", "britain", "british", "london"},
    "European Union": {"eu", "european", "brussels"},
    "France": {"france", "french"},
    "Germany": {"germany", "german"},
    "India": {"india", "indian", "modi"},
    "Pakistan": {"pakistan", "pakistani"},
    "Sudan": {"sudan", "sudanese"},
    "Burkina Faso": {"burkina", "faso"},
    "Congo": {"congo", "congolese"},
    "Venezuela": {"venezuela", "venezuelan"},
    "Cuba": {"cuba", "cuban"},
    "Japan": {"japan", "japanese"},
}

ACTOR_RULES = {
    "NATO": {"nato"},
    "European Union": {"eu", "european", "brussels"},
    "Trump administration": {"trump", "washington"},
    "Israeli government": {"israel", "israeli"},
    "Iranian government": {"iran", "iranian", "tehran"},
    "Hamas": {"hamas"},
    "Hezbollah": {"hezbollah"},
    "Russian government": {"russia", "putin", "moscow"},
    "Ukrainian government": {"ukraine", "zelensky", "kyiv"},
    "Chinese leadership": {"china", "beijing"},
}

TOPIC_RULES = [
    ("Russia-Ukraine", {"ukraine", "russia", "kyiv", "moscow", "zelensky", "putin"}),
    ("Israel-Palestine", {"gaza", "hamas", "west", "bank", "rafah", "palestinians", "israeli"}),
    ("Iran-Region", {"iran", "tehran", "hormuz", "nuclear", "gulf", "strait"}),
    ("China-Taiwan", {"china", "taiwan", "beijing", "taipei"}),
    ("US-China", {"china", "trade", "tariff", "washington", "beijing"}),
    ("Global Trade", {"trade", "tariff", "shipping", "sanctions", "oil"}),
    ("Military Build-Up", {"military", "troops", "missile", "navy", "defense", "army"}),
    ("Diplomatic Shift", {"summit", "diplomacy", "talks", "negotiation", "allies"}),
    ("Election Risk", {"election", "vote", "poll", "campaign"}),
    ("Africa Security", {"sudan", "sahel", "burkina", "congo", "jihadists", "coup"}),
]

REGION_RULES = [
    ("Middle East", {"israeli", "gaza", "hamas", "iran", "syria", "yemen", "hezbollah", "palestinians", "hormuz"}),
    ("Europe", {"ukraine", "russia", "europe", "eu", "nato", "france", "germany"}),
    ("Asia-Pacific", {"china", "taiwan", "japan", "korea", "india", "pakistan"}),
    ("Africa", {"sudan", "sahel", "congo", "somalia", "ethiopia", "niger", "burkina"}),
    ("Americas", {"united", "states", "washington", "venezuela", "canada", "mexico", "cuba"}),
]

STORY_RULES = [
    ("Iran and Gulf Tensions", {"iran", "hormuz", "tehran", "oil", "strait", "nuclear"}),
    ("Israel-Gaza and West Bank", {"gaza", "hamas", "west", "bank", "rafah", "settlers", "palestinians"}),
    ("Russia-Ukraine War", {"russia", "ukraine", "kyiv", "moscow", "putin", "zelensky"}),
    ("US-China and Taiwan", {"china", "taiwan", "beijing", "taipei", "tariff", "trade"}),
    ("Global Trade Frictions", {"tariff", "trade", "shipping", "sanctions", "oil"}),
    ("Sahel and African Security", {"burkina", "sudan", "sahel", "jihadists", "coup", "congo"}),
]

THEME_RULES = [
    ("War / Active Conflict", {"war", "strike", "missile", "troops", "attack", "army", "military"}),
    ("Great-Power Competition", {"china", "taiwan", "russia", "nato", "beijing", "washington"}),
    ("Trade / Sanctions", {"trade", "tariff", "sanctions", "shipping", "export", "imports"}),
    ("Energy Disruption", {"oil", "gas", "energy", "hormuz", "shipping"}),
    ("Military Build-Up", {"defense", "military", "navy", "missile", "troops", "army"}),
    ("Election with Global Consequences", {"election", "vote", "campaign", "poll"}),
    ("Diplomatic Shift", {"summit", "talks", "negotiation", "diplomacy", "allies"}),
]

GEOPOLITICAL_TERMS = {
    token
    for _, keywords in TOPIC_RULES + THEME_RULES
    for token in keywords
}
GEOPOLITICAL_TERMS.update(
    {
        "border",
        "foreign",
        "government",
        "president",
        "minister",
        "ceasefire",
        "conflict",
        "union",
    }
)

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "after",
    "over",
    "amid",
    "near",
    "says",
    "will",
    "could",
    "their",
    "about",
    "against",
    "under",
    "more",
    "world",
    "news",
    "what",
    "when",
    "where",
    "have",
    "has",
    "had",
}


@dataclass
class FeedItem:
    source: str
    title: str
    link: str
    published: str
    summary: str
    region_hint: str


def fetch_xml(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="ignore")


def get_text(element: ET.Element | None, *names: str) -> str:
    if element is None:
        return ""

    for name in names:
        child = element.find(name)
        if child is not None and child.text:
            return child.text.strip()

    return ""


def strip_html(value: str) -> str:
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
        pass

    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    return datetime.now(timezone.utc)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z\.\-']{2,}", text.lower())
        if token not in STOP_WORDS
    ]


def normalize_token(token: str) -> str:
    return token.strip(".'-")


def is_geopolitical(item: FeedItem) -> bool:
    tokens = {normalize_token(token) for token in tokenize(f"{item.title} {item.summary}")}
    return bool(tokens & GEOPOLITICAL_TERMS)


def parse_feed(feed: dict[str, str]) -> list[FeedItem]:
    raw_xml = fetch_xml(feed["url"])
    root = ET.fromstring(raw_xml)
    items: list[FeedItem] = []

    for node in root.findall(".//item")[:MAX_ITEMS_PER_FEED]:
        title = get_text(node, "title")
        link = get_text(node, "link")
        published = get_text(node, "pubDate", "published", "updated")
        summary = get_text(node, "description")

        item = FeedItem(
            source=feed["name"],
            title=strip_html(title),
            link=strip_html(link),
            published=published,
            summary=strip_html(summary),
            region_hint=feed["base_region"],
        )

        if item.title and item.link and is_geopolitical(item):
            items.append(item)

    return items


def classify_best_match(tokens: set[str], rules: list[tuple[str, set[str]]], fallback: str) -> str:
    best_name = fallback
    best_score = 0

    for name, keywords in rules:
        score = len(tokens & keywords)
        if score > best_score:
            best_name = name
            best_score = score

    return best_name


def classify_storyline(tokens: set[str], fallback: str) -> str:
    return classify_best_match(tokens, STORY_RULES, fallback)


def classify_topic(tokens: set[str]) -> str:
    return classify_best_match(tokens, TOPIC_RULES, "Global Affairs")


def classify_region(tokens: set[str], fallback: str) -> str:
    return classify_best_match(tokens, REGION_RULES, fallback)


def classify_theme(tokens: set[str]) -> str:
    return classify_best_match(tokens, THEME_RULES, "Strategic Shift")


def group_key(item: FeedItem) -> str:
    tokens = {normalize_token(token) for token in tokenize(f"{item.title} {item.summary}")}
    storyline = classify_storyline(tokens, "")
    if storyline:
        return storyline

    ranked = [token for token, _ in Counter(tokens).most_common() if token not in STOP_WORDS]
    if not ranked:
        return item.title.lower()
    return " ".join(sorted(ranked[:4]))


def detect_countries(tokens: set[str]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for country, keywords in COUNTRY_RULES.items():
        score = len(tokens & keywords)
        if score:
            ranked.append((score, country))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    countries = [country for _, country in ranked[:5]]
    return countries or ["Unclear from headlines"]


def detect_actors(tokens: set[str], countries: list[str]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for actor, keywords in ACTOR_RULES.items():
        score = len(tokens & keywords)
        if score:
            ranked.append((score, actor))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    actors = [actor for _, actor in ranked[:5]]
    actor_set = list(dict.fromkeys(countries + actors))
    return actor_set[:6]


def score_story(tokens: set[str], source_count: int, recent: datetime) -> tuple[float, str]:
    age_hours = max(0.0, (datetime.now(timezone.utc) - recent).total_seconds() / 3600)
    recency_bonus = max(0, 12 - age_hours)
    impact_bonus = sum(1 for _, keywords in THEME_RULES if tokens & keywords)
    score = source_count * 24 + recency_bonus + impact_bonus * 3

    if score >= 72:
        return score, "High"
    if score >= 50:
        return score, "Medium"
    return score, "Watch"


def build_market_impact(theme: str, countries: list[str], tokens: set[str]) -> str:
    joined = ", ".join(countries[:3])

    if theme == "Energy Disruption" or {"oil", "gas", "hormuz", "shipping"} & tokens:
        return f"Could move energy prices, shipping costs, inflation expectations, and defense-sensitive assets tied to {joined}."
    if theme == "Trade / Sanctions":
        return f"Could affect supply chains, tariff-sensitive sectors, industrial exporters, and currencies exposed to {joined}."
    if theme == "War / Active Conflict":
        return f"Could lift geopolitical risk premiums, support safe-haven flows, and pressure regional equities tied to {joined}."
    if theme == "Election with Global Consequences":
        return f"Could shift policy expectations, cross-border capital flows, and market pricing tied to {joined}."
    if theme == "Great-Power Competition":
        return f"Could influence semiconductor, shipping, defense, and currency markets connected to {joined}."
    return f"Could affect diplomatic expectations, regional stability, and investor risk appetite around {joined}."


def build_full_summary(storyline: str, topic: str, theme: str, region: str, source_names: list[str], countries: list[str]) -> str:
    country_text = ", ".join(countries[:4])
    summary_parts = [
        f"{storyline} is showing up as a {theme.lower()} story inside the broader {topic.lower()} file.",
        f"Recent coverage across {', '.join(source_names)} suggests the development is no longer isolated and is drawing attention across {region.lower()} reporting.",
        f"The main countries and systems touched by the story include {country_text}, which is why it has the potential to spill into markets, security planning, and diplomatic messaging over the next few days.",
    ]
    return " ".join(summary_parts)


def build_timeline(sources: list[dict]) -> list[dict]:
    timeline = []
    for source in sources[:4]:
        published = datetime.fromisoformat(source["published"]).astimezone()
        timeline.append(
            {
                "time": published.strftime("%b %d, %I:%M %p %Z"),
                "event": source["title"],
                "source": source["name"],
                "link": source["link"],
            }
        )
    return timeline


def build_strategic_significance(theme: str, topic: str, region: str, countries: list[str], source_count: int) -> str:
    country_text = ", ".join(countries[:3])
    return (
        f"Strategically, this sits at the intersection of {theme.lower()} and {topic.lower()}."
        f" If momentum builds, it could change how governments in and around {region.lower()} price risk, deploy leverage, and message allies or rivals."
        f" Cross-source pickup from {source_count} outlet{'s' if source_count != 1 else ''} suggests the signal is stronger than a single headline cycle around {country_text}."
    )


def build_effects(theme: str, countries: list[str], tokens: set[str]) -> dict:
    joined = ", ".join(countries[:3])
    market = build_market_impact(theme, countries, tokens)
    energy = (
        f"Energy channels may be affected if transport routes, oil supply expectations, or sanctions enforcement tied to {joined} begin to tighten."
        if {"oil", "gas", "energy", "shipping", "hormuz"} & tokens
        else f"Energy effects look secondary for now, but broader geopolitical risk could still lift commodity volatility around {joined}."
    )
    military = (
        f"Military planners may watch for force movements, strike risk, readiness changes, or signaling linked to {joined}."
        if {"war", "military", "troops", "missile", "army", "defense"} & tokens
        else f"Direct military effects look limited for now, though the situation could still influence deterrence and alliance planning tied to {joined}."
    )
    diplomatic = (
        f"Diplomatically, expect more public signaling, coalition management, and pressure campaigns involving {joined} over the next few days."
    )
    return {
        "market": market,
        "energy": energy,
        "military": military,
        "diplomatic": diplomatic,
    }


def build_paths(theme: str, storyline: str, countries: list[str]) -> dict:
    joined = ", ".join(countries[:3])
    return {
        "escalation": (
            f"Escalation case: {storyline} broadens because officials move from statements to concrete action such as tougher sanctions, force movements, retaliatory steps, or harder diplomatic red lines involving {joined}."
        ),
        "deescalation": (
            f"De-escalation case: the story cools if talks resume, military signaling softens, or policymakers frame the latest moves as bounded rather than open-ended across {joined}."
        ),
    }


def build_confidence(priority_score: float, source_count: int, sources: list[dict]) -> dict:
    if source_count >= 4:
        level = "High"
    elif source_count >= 2:
        level = "Medium"
    else:
        level = "Low"

    reason = (
        f"Confidence is {level.lower()} because the storyline appears across {source_count} distinct source"
        f"{'' if source_count == 1 else 's'}"
        f" and the top-ranked items are recent."
    )
    if sources:
        reason += f" The latest source in the cluster is {sources[0]['name']}."
    return {"level": level, "reason": reason}


def build_watch_next(tokens: set[str], countries: list[str], theme: str) -> list[str]:
    joined = ", ".join(countries[:3])
    watch_items = [
        f"Official statements or policy moves from {joined}.",
        "Whether additional major outlets converge on the same framing or reveal concrete new facts.",
    ]

    if theme == "Energy Disruption" or {"oil", "gas", "shipping", "hormuz"} & tokens:
        watch_items.append("Any sign of pressure on oil flows, shipping lanes, insurance costs, or refinery operations.")
    if theme == "Trade / Sanctions":
        watch_items.append("New tariffs, sanctions guidance, exemptions, or retaliation that could change supply-chain assumptions.")
    if theme == "War / Active Conflict":
        watch_items.append("Fresh military movements, strike reports, casualty updates, or ceasefire signals.")
    if theme == "Great-Power Competition":
        watch_items.append("Any new military signaling, technology restrictions, or alliance coordination measures.")

    return watch_items[:4]


def summarize_cluster(items: list[FeedItem]) -> dict:
    ordered = sorted(items, key=lambda item: parse_date(item.published), reverse=True)
    combined_tokens = [normalize_token(token) for token in tokenize(" ".join(f"{item.title} {item.summary}" for item in ordered))]
    token_set = set(combined_tokens)
    recent = parse_date(ordered[0].published)
    source_names = list(dict.fromkeys(item.source for item in ordered))
    storyline = classify_storyline(token_set, ordered[0].title)
    topic = classify_topic(token_set)
    region = classify_region(token_set, ordered[0].region_hint)
    theme = classify_theme(token_set)
    countries = detect_countries(token_set)
    actors = detect_actors(token_set, countries)
    impact_score, priority = score_story(token_set, len(source_names), recent)

    unique_sources = []
    seen_sources = set()
    for item in ordered:
        if item.source in seen_sources:
            continue
        seen_sources.add(item.source)
        unique_sources.append(
            {
                "name": item.source,
                "title": item.title,
                "link": item.link,
                "published": parse_date(item.published).isoformat(),
            }
        )

    primary_source = unique_sources[0]
    supporting_sources = [source["name"] for source in unique_sources[1:4]]
    full_summary = build_full_summary(storyline, topic, theme, region, source_names, countries)
    effects = build_effects(theme, countries, token_set)
    timeline = build_timeline(unique_sources)
    strategic_significance = build_strategic_significance(theme, topic, region, countries, len(source_names))
    paths = build_paths(theme, storyline, countries)
    confidence = build_confidence(impact_score, len(source_names), unique_sources)
    watch_next = build_watch_next(token_set, countries, theme)

    why_it_matters = (
        f"This falls under {theme.lower()} within {topic.lower()},"
        f" with potential spillover across {region.lower()} decision-making."
    )
    if len(source_names) > 1:
        why_it_matters += f" It showed up across {len(source_names)} separate outlets, which raises confidence that it is consequential."

    return {
        "id": re.sub(r"[^a-z0-9]+", "-", storyline.lower()).strip("-"),
        "headline": storyline,
        "topic": topic,
        "theme": theme,
        "region": region,
        "priority": priority,
        "priority_score": round(impact_score, 1),
        "source_count": len(source_names),
        "card_blurb": (
            f"{theme} signal across {len(source_names)} source"
            f"{'' if len(source_names) == 1 else 's'}."
        ),
        "countries_involved": countries,
        "actors_involved": actors,
        "why_it_matters": why_it_matters,
        "possible_market_or_global_impact": build_market_impact(theme, countries, token_set),
        "full_summary": full_summary,
        "timeline": timeline,
        "strategic_significance": strategic_significance,
        "effects": effects,
        "paths": paths,
        "confidence": confidence,
        "watch_next": watch_next,
        "source_link": primary_source["link"],
        "source_name": primary_source["name"],
        "supporting_sources": supporting_sources,
        "latest_published": recent.isoformat(),
        "summary": (
            f"{storyline} combines recent reporting from {', '.join(source_names)}."
        ),
        "sources": unique_sources[:5],
    }


def cluster_items(items: Iterable[FeedItem]) -> list[dict]:
    buckets: dict[str, list[FeedItem]] = defaultdict(list)

    for item in items:
        buckets[group_key(item)].append(item)

    clusters = [summarize_cluster(group) for group in buckets.values()]
    clusters = [
        cluster
        for cluster in clusters
        if cluster["source_count"] >= 2 or cluster["priority"] != "Watch"
    ]
    clusters.sort(
        key=lambda cluster: (
            cluster["priority_score"],
            cluster["latest_published"],
        ),
        reverse=True,
    )
    return clusters[:MAX_STORIES]


def build_briefing() -> dict:
    all_items: list[FeedItem] = []
    failures: list[str] = []

    for feed in FEEDS:
        try:
            all_items.extend(parse_feed(feed))
        except Exception as exc:
            failures.append(f"{feed['name']}: {exc}")

    stories = cluster_items(all_items)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [feed["name"] for feed in FEEDS],
        "notes": [
            "This report favors multiple-source overlap, high-impact themes, and restrained language.",
            "It aims for neutrality in tone, not a claim of perfect objectivity.",
        ],
        "fetch_failures": failures,
        "stories": stories,
    }


def render_markdown(briefing: dict) -> str:
    generated = datetime.fromisoformat(briefing["generated_at"]).astimezone()
    lines = [
        "# Quiet Current Geopolitical Report",
        "",
        f"Generated: {generated.strftime('%Y-%m-%d %I:%M %p %Z')}",
        "",
        "## Scope",
        "",
        "This scan prioritizes wars, great-power competition, trade conflicts, sanctions, energy disruptions, military buildups, elections with global consequences, and major diplomatic shifts.",
        "",
        "## Major Developments",
        "",
    ]

    if not briefing["stories"]:
        lines.extend(
            [
                "No major geopolitical stories passed the current filters.",
                "",
            ]
        )

    for index, story in enumerate(briefing["stories"], start=1):
        lines.extend(
            [
                f"### {index}. {story['headline']}",
                "",
                f"- Priority: {story['priority']}",
                f"- Theme: {story['theme']}",
                f"- Countries involved: {', '.join(story['countries_involved'])}",
                f"- Why it matters: {story['why_it_matters']}",
                f"- Possible market or global impact: {story['possible_market_or_global_impact']}",
                f"- Confidence: {story['confidence']['level']} ({story['confidence']['reason']})",
                f"- Source: [{story['source_name']}]({story['source_link']})",
            ]
        )

        if story["supporting_sources"]:
            lines.append(f"- Supporting source spread: {', '.join(story['supporting_sources'])}")

        lines.extend(["", f"Headline basis: {story['summary']}", ""])

    if briefing["fetch_failures"]:
        lines.extend(
            [
                "## Feed Notes",
                "",
                *[f"- {failure}" for failure in briefing["fetch_failures"]],
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def write_outputs(briefing: dict, markdown: str) -> tuple[Path, Path]:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    timestamped_markdown_path = REPORTS_DIR / f"report-{timestamp}.md"
    JSON_OUTPUT_PATH.write_text(json.dumps(briefing, indent=2), encoding="utf-8")
    LATEST_MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
    timestamped_markdown_path.write_text(markdown, encoding="utf-8")
    return JSON_OUTPUT_PATH, timestamped_markdown_path


def main() -> int:
    briefing = build_briefing()
    markdown = render_markdown(briefing)
    json_path, markdown_path = write_outputs(briefing, markdown)

    print(markdown)
    print(f"Saved JSON briefing to {json_path}")
    print(f"Saved markdown report to {markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
