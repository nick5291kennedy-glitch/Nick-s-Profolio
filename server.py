#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional


HOST = "127.0.0.1"
PORT = 8000
BASE_DIR = Path(__file__).resolve().parent
CACHE_TTL_SECONDS = 300


ASSETS = [
    {
        "name": "Ondo",
        "ticker": "ONDO",
        "type": "Crypto",
        "yahoo_symbol": "ONDO-USD",
        "news_query": "Ondo Finance OR ONDO crypto",
    },
    {
        "name": "Chainlink",
        "ticker": "LINK",
        "type": "Crypto",
        "yahoo_symbol": "LINK-USD",
        "news_query": "Chainlink OR LINK crypto",
    },
    {
        "name": "Bitcoin",
        "ticker": "BTC",
        "type": "Crypto",
        "yahoo_symbol": "BTC-USD",
        "news_query": "Bitcoin OR BTC crypto",
    },
    {
        "name": "Ethereum",
        "ticker": "ETH",
        "type": "Crypto",
        "yahoo_symbol": "ETH-USD",
        "news_query": "Ethereum OR ETH crypto",
    },
    {
        "name": "Cameco",
        "ticker": "CCJ",
        "type": "Stock",
        "yahoo_symbol": "CCJ",
        "news_query": "Cameco OR CCJ stock",
    },
    {
        "name": "Archer Aviation",
        "ticker": "ACHR",
        "type": "Stock",
        "yahoo_symbol": "ACHR",
        "news_query": "Archer Aviation OR ACHR stock",
    },
    {
        "name": "AST SpaceMobile",
        "ticker": "ASTS",
        "type": "Stock",
        "yahoo_symbol": "ASTS",
        "news_query": "AST SpaceMobile OR ASTS stock",
    },
    {
        "name": "UnitedHealth",
        "ticker": "UNH",
        "type": "Stock",
        "yahoo_symbol": "UNH",
        "news_query": "UnitedHealth OR UNH stock",
    },
]


cache_lock = threading.Lock()
cache_payload: Optional[dict] = None
cache_time = 0.0

POSITIVE_KEYWORDS = {
    "surge",
    "rally",
    "gain",
    "beat",
    "approval",
    "partnership",
    "launch",
    "expansion",
    "growth",
    "record",
    "bullish",
    "upgrade",
    "wins",
    "strong",
}

NEGATIVE_KEYWORDS = {
    "drop",
    "fall",
    "miss",
    "downgrade",
    "lawsuit",
    "probe",
    "delay",
    "cut",
    "risk",
    "warning",
    "selloff",
    "bearish",
    "decline",
    "weak",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def fetch_json(url: str, headers: Optional[dict] = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, headers: Optional[dict] = None) -> str:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


def safe_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None

    return number


def average(values: List[float]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def stddev(values: List[float]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    if len(clean) < 2:
        return None
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / len(clean)
    return math.sqrt(variance)


def quantile(values: List[float], percentile: float) -> Optional[float]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]

    position = (len(clean) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return clean[lower]

    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def percent_change(start: Optional[float], end: Optional[float]) -> Optional[float]:
    if start in (None, 0) or end is None:
        return None
    return ((end - start) / start) * 100


def series_change_percent(series: List[dict]) -> Optional[float]:
    if len(series) < 2:
        return None
    return percent_change(series[0]["close"], series[-1]["close"])


def trim_series(series: List[dict], max_points: int) -> List[dict]:
    if len(series) <= max_points:
        return series

    step = len(series) / max_points
    trimmed = []
    for index in range(max_points):
        trimmed.append(series[min(int(index * step), len(series) - 1)])
    return trimmed


def recent_returns(series: List[dict]) -> List[float]:
    returns = []
    for index in range(1, len(series)):
        previous = series[index - 1]["close"]
        current = series[index]["close"]
        change = percent_change(previous, current)
        if change is not None:
            returns.append(change)
    return returns


def yahoo_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://finance.yahoo.com",
        "Referer": "https://finance.yahoo.com/",
    }


def fetch_yahoo_chart(symbol: str, chart_range: str, interval: str) -> dict:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={chart_range}&includePrePost=false&events=div%2Csplits"
    )
    payload = fetch_json(url, headers=yahoo_headers())
    return payload["chart"]["result"][0]


def parse_yahoo_series(result: dict) -> List[dict]:
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {}).get("quote", [{}])[0]
    closes = indicators.get("close") or []
    volumes = indicators.get("volume") or []
    series = []

    for index, (timestamp, close) in enumerate(zip(timestamps, closes)):
        price = safe_float(close)
        if price is None:
            continue

        volume = safe_float(volumes[index]) if index < len(volumes) else None
        series.append(
            {
                "timestamp": int(timestamp) * 1000,
                "close": round(price, 6),
                "volume": volume,
            }
        )

    return series


def build_chart_view(title: str, label: str, series: List[dict], message: Optional[str] = None) -> dict:
    status = "ok" if series else "unavailable"
    return {
        "title": title,
        "label": label,
        "series": series,
        "status": status,
        "message": message or ("Chart unavailable from the current data source." if status != "ok" else ""),
        "performancePercent": series_change_percent(series),
    }


def fetch_chart_view(symbol: str, chart_range: str, interval: str, title: str, label: str, max_points: int) -> dict:
    try:
        result = fetch_yahoo_chart(symbol, chart_range, interval)
        series = trim_series(parse_yahoo_series(result), max_points)
        if not series:
            return build_chart_view(title, label, [], "No usable candles were returned by Yahoo Finance.")
        return build_chart_view(title, label, series)
    except Exception as error:
        return build_chart_view(title, label, [], f"Yahoo Finance chart request failed: {error}")


def relative_time(value: Optional[datetime]) -> str:
    if value is None:
        return "recently"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    delta = datetime.now(timezone.utc) - value.astimezone(timezone.utc)
    hours = int(delta.total_seconds() // 3600)

    if hours < 1:
        return "within the last hour"
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def parse_google_news(query: str, limit: int = 3) -> List[dict]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    xml_text = fetch_text(url, headers={"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(xml_text)
    headlines = []

    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        source = item.findtext("source", "Google News").strip()
        published = item.findtext("pubDate", "").strip()
        published_dt = None

        if published:
            try:
                published_dt = parsedate_to_datetime(published)
            except (TypeError, ValueError):
                published_dt = None

        headlines.append(
            {
                "title": title,
                "link": link,
                "source": source or "Google News",
                "publishedAt": published_dt.isoformat() if published_dt else published,
                "publishedRelative": relative_time(published_dt),
            }
        )

    return headlines


def summarize_news_tone(headlines: List[dict]) -> dict:
    positive = 0
    negative = 0

    for headline in headlines:
        title = headline["title"].lower()
        if any(keyword in title for keyword in POSITIVE_KEYWORDS):
            positive += 1
        if any(keyword in title for keyword in NEGATIVE_KEYWORDS):
            negative += 1

    tone_score = positive - negative
    if tone_score > 0:
        label = "Constructive"
    elif tone_score < 0:
        label = "Cautious"
    else:
        label = "Mixed"

    return {"positive": positive, "negative": negative, "label": label, "score": tone_score}


def direction_label(change: Optional[float], threshold: float = 1.0) -> str:
    if change is None:
        return "Unavailable"
    if change > threshold:
        return "Up"
    if change < -threshold:
        return "Down"
    return "Sideways"


def volatility_label(value: Optional[float], asset_type: str) -> str:
    if value is None:
        return "Unknown"

    low_cutoff = 1.3 if asset_type == "Stock" else 2.0
    high_cutoff = 2.8 if asset_type == "Stock" else 4.5

    if value < low_cutoff:
        return "Low"
    if value < high_cutoff:
        return "Medium"
    return "High"


def trend_quality_label(alignment_score: int, monthly_change: Optional[float]) -> str:
    if alignment_score >= 3 and (monthly_change or 0) > 0:
        return "Strong"
    if alignment_score >= 2:
        return "Decent"
    if alignment_score <= 0:
        return "Poor"
    return "Mixed"


def build_zone_text(level: Optional[float], fallback: str = "Unavailable") -> str:
    if level is None:
        return fallback

    precision = 4 if level < 10 else 2 if level < 1000 else 0
    return f"${level:,.{precision}f}"


def build_technical_analysis(asset: dict, day_view: dict, week_view: dict, month_view: dict, current_price: Optional[float], headlines: List[dict]) -> dict:
    day_change = day_view["performancePercent"]
    week_change = week_view["performancePercent"]
    month_change = month_view["performancePercent"]
    month_series = month_view["series"]
    week_series = week_view["series"]
    day_series = day_view["series"]
    news_tone = summarize_news_tone(headlines)
    complete_chart_set = all(view["status"] == "ok" for view in [day_view, week_view, month_view])

    monthly_closes = [point["close"] for point in month_series]
    weekly_closes = [point["close"] for point in week_series]
    monthly_returns = recent_returns(month_series)
    volatility_value = stddev(monthly_returns)
    volatility = volatility_label(volatility_value, asset["type"])
    support = quantile(monthly_closes[-20:], 0.2) if monthly_closes else None
    resistance = quantile(monthly_closes[-20:], 0.8) if monthly_closes else None
    month_low = min(monthly_closes) if monthly_closes else None
    month_high = max(monthly_closes) if monthly_closes else None
    position_in_range = None

    if current_price is not None and month_low is not None and month_high is not None and month_high != month_low:
        position_in_range = ((current_price - month_low) / (month_high - month_low)) * 100

    short_avg = average([point["close"] for point in month_series[-5:]]) if month_series else None
    long_avg = average([point["close"] for point in month_series[-20:]]) if month_series else None
    moving_average_bias = percent_change(long_avg, short_avg)

    day_direction = direction_label(day_change, 0.6 if asset["type"] == "Stock" else 1.0)
    week_direction = direction_label(week_change, 1.0 if asset["type"] == "Stock" else 2.0)
    month_direction = direction_label(month_change, 2.0 if asset["type"] == "Stock" else 3.0)
    alignment_score = sum(direction == "Up" for direction in [day_direction, week_direction, month_direction])
    if day_direction == "Down":
        alignment_score -= 1
    if week_direction == "Down":
        alignment_score -= 1
    if month_direction == "Down":
        alignment_score -= 1

    trend_quality = trend_quality_label(alignment_score, month_change)
    momentum_value = average([
        day_change,
        week_change * 1.2 if week_change is not None else None,
        month_change * 1.4 if month_change is not None else None,
        moving_average_bias,
    ])

    if momentum_value is None:
        momentum_summary = "Momentum unavailable"
    elif momentum_value > 4:
        momentum_summary = "Strong positive momentum"
    elif momentum_value > 1:
        momentum_summary = "Constructive momentum"
    elif momentum_value < -4:
        momentum_summary = "Clear downside momentum"
    elif momentum_value < -1:
        momentum_summary = "Momentum is fading"
    else:
        momentum_summary = "Momentum is balanced"

    breakout_risk = "Neutral"
    breakout_detail = "Price is not pressing a major monthly edge."
    distance_to_support = None
    distance_to_resistance = None

    if current_price is not None and support not in (None, 0):
        distance_to_support = ((current_price - support) / support) * 100
    if current_price is not None and resistance not in (None, 0):
        distance_to_resistance = ((resistance - current_price) / current_price) * 100

    if distance_to_resistance is not None and distance_to_resistance <= 2 and (month_change or 0) > 0:
        breakout_risk = "Breakout test"
        breakout_detail = "Price is close to resistance, so follow-through matters."
    elif distance_to_support is not None and distance_to_support <= 2 and (month_change or 0) < 0:
        breakout_risk = "Breakdown risk"
        breakout_detail = "Price is leaning on support, so a weak tape could break it."

    volume_values = [point["volume"] for point in month_series if point.get("volume") is not None]
    volume_available = len(volume_values) >= 10
    recent_volume = average(volume_values[-5:]) if volume_available else None
    baseline_volume = average(volume_values[-20:-5]) if volume_available and len(volume_values) > 20 else average(volume_values[:-5]) if volume_available else None
    volume_change = percent_change(baseline_volume, recent_volume)

    if volume_change is None:
        volume_summary = "Volume unavailable"
    elif volume_change > 15 and (week_change or 0) > 0:
        volume_summary = "Volume is supporting the recent move"
    elif volume_change > 15 and (week_change or 0) <= 0:
        volume_summary = "Volume is elevated during a weak patch"
    elif volume_change < -15:
        volume_summary = "Participation has cooled off"
    else:
        volume_summary = "Volume is near its recent baseline"

    price_news_alignment = "Mixed"
    if news_tone["score"] > 0 and (week_change or 0) > 0:
        price_news_alignment = "Price action broadly aligns with constructive news"
    elif news_tone["score"] < 0 and (week_change or 0) < 0:
        price_news_alignment = "Price action broadly aligns with cautious news"
    elif news_tone["score"] == 0:
        price_news_alignment = "News is mixed, so price is doing more of the talking"
    else:
        price_news_alignment = "Price action and news tone are diverging"

    trend_score = clamp(
        12 + (month_change or 0) * 0.8 + (week_change or 0) * 0.5 + alignment_score * 3,
        0,
        25,
    )
    momentum_score = clamp(10 + (momentum_value or 0) * 1.2, 0, 20)

    if volatility == "Low":
        volatility_score = 9
    elif volatility == "Medium":
        volatility_score = 6
    elif volatility == "High":
        volatility_score = 2 if (month_change or 0) < 0 else 4
    else:
        volatility_score = 4

    sr_score = 7
    if distance_to_support is not None and distance_to_resistance is not None:
        upside_room = max(distance_to_resistance, -20)
        downside_room = max(distance_to_support, -20)
        rr_proxy = upside_room - downside_room
        sr_score = clamp(7 + rr_proxy * 0.6, 0, 15)

    highs_lows_score = 5
    if position_in_range is not None:
        if 45 <= position_in_range <= 75 and (month_change or 0) > 0:
            highs_lows_score = 8
        elif position_in_range < 20 and (month_change or 0) < 0:
            highs_lows_score = 2
        elif position_in_range > 85 and (month_change or 0) < 0:
            highs_lows_score = 3
        elif position_in_range > 60:
            highs_lows_score = 6

    volume_score = 5
    if volume_change is not None:
        volume_score = clamp(5 + volume_change * 0.1, 0, 10)

    news_score = clamp(2.5 + news_tone["score"] * 1.2, 0, 5)
    risk_score = 5
    if volatility == "High":
        risk_score -= 2
    if not complete_chart_set:
        risk_score -= 2
    if distance_to_support is not None and distance_to_support < 1 and (week_change or 0) < 0:
        risk_score -= 1
    risk_score = clamp(risk_score, 0, 5)

    total_score = round(
        trend_score
        + momentum_score
        + volatility_score
        + sr_score
        + highs_lows_score
        + volume_score
        + news_score
        + risk_score
    )

    confidence = 38
    confidence += sum(view["status"] == "ok" for view in [day_view, week_view, month_view]) * 9
    confidence += 5 if volume_available else -5
    confidence += min(len(headlines), 3) * 2
    confidence -= 8 if volatility == "High" else 0
    confidence -= 3 if news_tone["label"] == "Mixed" else 0
    confidence = round(clamp(confidence, 25, 82))

    if not complete_chart_set:
        confidence = max(25, confidence - 18)

    if confidence < 45 and volatility == "High":
        recommendation_label = "High risk"
    elif total_score >= 78:
        recommendation_label = "Strong bullish"
    elif total_score >= 64:
        recommendation_label = "Bullish"
    elif total_score >= 48:
        recommendation_label = "Neutral"
    elif total_score >= 35:
        recommendation_label = "Bearish"
    else:
        recommendation_label = "High risk"

    timeframe = "Swing"
    if abs(day_change or 0) > abs(month_change or 0) and abs(day_change or 0) > 2:
        timeframe = "Short"
    elif abs(month_change or 0) >= abs(week_change or 0) and abs(month_change or 0) > 4:
        timeframe = "Medium"

    key_reasons = []
    risks = []
    strengthen = []
    weaken = []

    if month_direction == "Up":
        key_reasons.append("1M trend is still pointing higher.")
    if week_direction == "Up":
        key_reasons.append("1W trend is supporting the setup.")
    if momentum_value is not None and momentum_value > 1:
        key_reasons.append(momentum_summary + ".")
    if volume_change is not None and volume_change > 10:
        key_reasons.append(volume_summary + ".")
    if news_tone["score"] > 0:
        key_reasons.append("Headline tone is modestly constructive.")

    if volatility == "High":
        risks.append("Volatility is high, so timing risk is elevated.")
    if month_direction == "Down":
        risks.append("1M trend is still leaning lower.")
    if breakout_risk == "Breakdown risk":
        risks.append("Price is sitting close to support.")
    if news_tone["score"] < 0:
        risks.append("Recent headlines lean cautious.")
    if not complete_chart_set:
        risks.append("At least one chart window is missing.")

    if resistance is not None:
        strengthen.append(f"A decisive move above {build_zone_text(resistance)} would improve the setup.")
        weaken.append(f"Repeated rejection near {build_zone_text(resistance)} would weaken the setup.")
    if support is not None:
        strengthen.append(f"Holding above {build_zone_text(support)} would keep the base intact.")
        weaken.append(f"A clean break below {build_zone_text(support)} would damage the structure.")
    if volume_available:
        strengthen.append("Stronger volume behind up moves would raise conviction.")
        weaken.append("Shrinking participation during bounces would reduce conviction.")
    else:
        strengthen.append("Cleaner volume confirmation would make the read more reliable.")
        weaken.append("Missing volume data limits conviction.")

    if not key_reasons:
        key_reasons.append("The setup is mixed, so no single edge dominates.")
    if not risks:
        risks.append("No single invalidation risk dominates right now.")

    bullish_scenario = (
        f"Bulls want price to hold support near {build_zone_text(support)} and push toward "
        f"{build_zone_text(resistance)} with improving momentum."
    )
    bearish_scenario = (
        f"Bears would gain control if price loses {build_zone_text(support)} or fails repeatedly "
        f"under {build_zone_text(resistance)}."
    )

    risk_reward = clamp(sr_score * 2 + trend_score * 0.4 - (10 - volatility_score), 0, 100)

    return {
        "trendDirections": {"1D": day_direction, "1W": week_direction, "1M": month_direction},
        "momentumSummary": momentum_summary,
        "supportZone": build_zone_text(support),
        "resistanceZone": build_zone_text(resistance),
        "volatilityLevel": volatility,
        "volatilityValue": None if volatility_value is None else round(volatility_value, 2),
        "breakoutBreakdownRisk": breakout_risk,
        "breakoutBreakdownDetail": breakout_detail,
        "trendQuality": trend_quality,
        "priceNewsAlignment": price_news_alignment,
        "highLowPosition": "Unavailable" if position_in_range is None else f"{position_in_range:.0f}% of 1M range",
        "volumeSummary": volume_summary,
        "bullishScenario": bullish_scenario,
        "bearishScenario": bearish_scenario,
        "scoringBreakdown": [
            {"name": "Trend", "score": round(trend_score), "max": 25, "detail": f"1D {day_direction}, 1W {week_direction}, 1M {month_direction}."},
            {"name": "Momentum", "score": round(momentum_score), "max": 20, "detail": momentum_summary + "."},
            {"name": "Volatility", "score": round(volatility_score), "max": 10, "detail": f"Volatility is {volatility.lower()}."},
            {"name": "Support / Resistance", "score": round(sr_score), "max": 15, "detail": f"Support near {build_zone_text(support)} and resistance near {build_zone_text(resistance)}."},
            {"name": "Highs / Lows", "score": round(highs_lows_score), "max": 10, "detail": f"Price sits at {('unknown' if position_in_range is None else f'{position_in_range:.0f}%')} of the 1M range."},
            {"name": "Volume", "score": round(volume_score), "max": 10, "detail": volume_summary + "."},
            {"name": "News Tone", "score": round(news_score), "max": 5, "detail": f"Headline tone is {news_tone['label'].lower()}."},
            {"name": "Risk Factors", "score": round(risk_score), "max": 5, "detail": "Higher score means fewer active invalidation risks."},
        ],
        "recommendation": {
            "label": recommendation_label,
            "score": total_score,
            "confidence": confidence,
            "timeframe": timeframe,
            "keyReasons": key_reasons[:4],
            "risks": risks[:4],
            "strengthen": strengthen[:4],
            "weaken": weaken[:4],
            "riskRewardScore": round(risk_reward),
        },
        "newsTone": news_tone,
    }


def build_summary(asset: dict) -> str:
    daily = asset["dailyChangePercent"]
    weekly = asset["weeklyChangePercent"]
    monthly = asset["monthlyChangePercent"]
    analysis = asset["analysis"]

    daily_text = "flat on the day"
    if daily is not None:
        if daily > 0.5:
            daily_text = f"up {daily:.2f}% on the day"
        elif daily < -0.5:
            daily_text = f"down {abs(daily):.2f}% on the day"

    weekly_text = "with limited 1W context"
    if weekly is not None:
        weekly_text = f"while the 1W move sits at {weekly:.2f}%"

    monthly_text = ""
    if monthly is not None:
        monthly_text = f" The 1M move is {monthly:.2f}%."

    return (
        f"{asset['name']} is {daily_text}, {weekly_text}. "
        f"Trend quality looks {analysis['trendQuality'].lower()}, "
        f"volatility is {analysis['volatilityLevel'].lower()}, and news alignment is "
        f"{analysis['priceNewsAlignment'].lower()}."
        f"{monthly_text}"
    )


def build_signal_lists(asset: dict) -> dict:
    analysis = asset["analysis"]
    daily = asset["dailyChangePercent"]
    weekly = asset["weeklyChangePercent"]
    monthly = asset["monthlyChangePercent"]
    bullish = []
    bearish = []

    if analysis["trendDirections"]["1M"] == "Up":
        bullish.append("1M trend is still pointing higher.")
    if analysis["trendDirections"]["1W"] == "Up":
        bullish.append("1W trend is supporting the setup.")
    if analysis["newsTone"]["score"] > 0:
        bullish.append("Headline tone is more constructive than negative.")
    if analysis["volumeSummary"] == "Volume is supporting the recent move":
        bullish.append("Volume is confirming the recent move.")

    if daily is not None and daily < -1:
        bearish.append(f"Price is lower on the day by {abs(daily):.2f}%.")
    if weekly is not None and weekly < -3:
        bearish.append(f"1W performance is soft at {weekly:.2f}%.")
    if monthly is not None and monthly < -5:
        bearish.append(f"1M performance remains weak at {monthly:.2f}%.")
    if analysis["breakoutBreakdownRisk"] == "Breakdown risk":
        bearish.append("Price is leaning on support.")
    if analysis["newsTone"]["score"] < 0:
        bearish.append("Recent headlines lean cautious.")

    if not bullish:
        bullish.append("No decisive upside signal is standing out right now.")
    if not bearish:
        bearish.append("No dominant downside trigger is active right now.")

    return {"bullish": bullish[:3], "bearish": bearish[:3]}


def build_asset_from_yahoo(asset_config: dict) -> dict:
    day_result = fetch_yahoo_chart(asset_config["yahoo_symbol"], "1d", "5m")
    meta = day_result.get("meta", {})
    current_price = safe_float(meta.get("regularMarketPrice"))

    chart_views = [
        fetch_chart_view(asset_config["yahoo_symbol"], "1d", "5m", "1D", "5m candles", 96),
        fetch_chart_view(asset_config["yahoo_symbol"], "7d", "1h", "1W", "1h candles", 84),
        fetch_chart_view(asset_config["yahoo_symbol"], "1mo", "1d", "1M", "1d candles", 32),
    ]

    headlines = parse_google_news(asset_config["news_query"])
    asset = {
        "name": asset_config["name"],
        "ticker": asset_config["ticker"],
        "type": asset_config["type"],
        "currentPrice": current_price,
        "dailyChangePercent": chart_views[0]["performancePercent"],
        "weeklyChangePercent": chart_views[1]["performancePercent"],
        "monthlyChangePercent": chart_views[2]["performancePercent"],
        "chartViews": chart_views,
        "priceContext": "Yahoo Finance market feed",
        "headlines": headlines,
        "notice": None,
    }

    complete_chart_set = all(view["status"] == "ok" for view in chart_views)
    if not complete_chart_set:
        missing = ", ".join(view["title"] for view in chart_views if view["status"] != "ok")
        asset["notice"] = f"Some chart windows are unavailable: {missing}. Confidence has been reduced."

    asset["analysis"] = build_technical_analysis(asset, chart_views[0], chart_views[1], chart_views[2], current_price, headlines)
    asset["trend"] = asset["analysis"]["recommendation"]["label"]
    signals = build_signal_lists(asset)
    asset["bullishSignals"] = signals["bullish"]
    asset["bearishSignals"] = signals["bearish"]
    asset["summary"] = build_summary(asset)
    return asset


def fallback_asset(asset_config: dict, error: Exception) -> dict:
    headlines = parse_google_news(asset_config["news_query"])
    asset = {
        "name": asset_config["name"],
        "ticker": asset_config["ticker"],
        "type": asset_config["type"],
        "currentPrice": None,
        "dailyChangePercent": None,
        "weeklyChangePercent": None,
        "monthlyChangePercent": None,
        "chartViews": [
            build_chart_view("1D", "5m candles", [], "Chart data is unavailable from the upstream source."),
            build_chart_view("1W", "1h candles", [], "Chart data is unavailable from the upstream source."),
            build_chart_view("1M", "1d candles", [], "Chart data is unavailable from the upstream source."),
        ],
        "priceContext": "Live market feed unavailable",
        "notice": f"Live market fetch failed: {error}",
        "headlines": headlines,
    }
    asset["analysis"] = {
        "trendDirections": {"1D": "Unavailable", "1W": "Unavailable", "1M": "Unavailable"},
        "momentumSummary": "Momentum unavailable because chart data is missing.",
        "supportZone": "Unavailable",
        "resistanceZone": "Unavailable",
        "volatilityLevel": "Unknown",
        "volatilityValue": None,
        "breakoutBreakdownRisk": "Unknown",
        "breakoutBreakdownDetail": "Chart data is unavailable, so no breakout or breakdown read is shown.",
        "trendQuality": "Poor",
        "priceNewsAlignment": "Cannot compare price and news without market data",
        "highLowPosition": "Unavailable",
        "volumeSummary": "Volume unavailable",
        "bullishScenario": "Bullish scenario is withheld until chart data returns.",
        "bearishScenario": "Bearish scenario is withheld until chart data returns.",
        "scoringBreakdown": [
            {"name": "Trend", "score": 0, "max": 25, "detail": "Chart data unavailable."},
            {"name": "Momentum", "score": 0, "max": 20, "detail": "Chart data unavailable."},
            {"name": "Volatility", "score": 0, "max": 10, "detail": "Chart data unavailable."},
            {"name": "Support / Resistance", "score": 0, "max": 15, "detail": "Chart data unavailable."},
            {"name": "Highs / Lows", "score": 0, "max": 10, "detail": "Chart data unavailable."},
            {"name": "Volume", "score": 0, "max": 10, "detail": "Volume unavailable."},
            {"name": "News Tone", "score": 2, "max": 5, "detail": "Headlines are still shown, but price is missing."},
            {"name": "Risk Factors", "score": 0, "max": 5, "detail": "Confidence reduced due to missing data."},
        ],
        "recommendation": {
            "label": "High risk",
            "score": 2,
            "confidence": 25,
            "timeframe": "Short",
            "keyReasons": ["Recommendation withheld because price data is unavailable."],
            "risks": ["The upstream market data source failed."],
            "strengthen": ["Restore working chart data for this asset."],
            "weaken": ["Another failed refresh would keep the read unusable."],
            "riskRewardScore": 0,
        },
        "newsTone": summarize_news_tone(headlines),
    }
    asset["trend"] = "High risk"
    asset["bullishSignals"] = ["No bullish chart signal is shown while data is missing."]
    asset["bearishSignals"] = ["Market data is unavailable, so the asset is treated as high risk."]
    asset["summary"] = (
        f"{asset['name']} headlines are available, but the market data feed failed, "
        "so no chart-based recommendation is shown."
    )
    return asset


def summarize_market_tone(assets: List[dict]) -> str:
    average_score = average([asset["analysis"]["recommendation"]["score"] for asset in assets])
    average_weekly = average([asset["weeklyChangePercent"] for asset in assets if asset["weeklyChangePercent"] is not None])
    positive_count = sum(asset["analysis"]["recommendation"]["score"] >= 64 for asset in assets)

    if average_score is None:
        return "Mixed"
    if average_score >= 65 and (average_weekly or 0) > 0 and positive_count >= 4:
        return "Constructive"
    if average_score <= 40 or (average_weekly or 0) < -2:
        return "Cautious"
    return "Mixed"


def build_recommendations(assets: List[dict]) -> dict:
    ranked = []
    for asset in assets:
        recommendation = asset["analysis"]["recommendation"]
        ranked.append(
            {
                "ticker": asset["ticker"],
                "name": asset["name"],
                "type": asset["type"],
                "label": recommendation["label"],
                "score": recommendation["score"],
                "confidence": recommendation["confidence"],
                "timeframe": recommendation["timeframe"],
                "keyReasons": recommendation["keyReasons"],
                "risks": recommendation["risks"],
                "strengthen": recommendation["strengthen"],
                "weaken": recommendation["weaken"],
                "riskRewardScore": recommendation["riskRewardScore"],
                "scoringBreakdown": asset["analysis"]["scoringBreakdown"],
            }
        )

    ranked.sort(key=lambda item: (-item["score"], -item["confidence"], -item["riskRewardScore"]))

    strongest_crypto = next((item for item in ranked if item["type"] == "Crypto"), None)
    strongest_stock = next((item for item in ranked if item["type"] == "Stock"), None)
    highest_risk = min(ranked, key=lambda item: (item["confidence"], item["score"]))
    eligible_for_rr = [item for item in ranked if item["label"] != "High risk"] or ranked
    best_risk_reward = max(
        eligible_for_rr,
        key=lambda item: item["riskRewardScore"] + item["score"] * 0.35 + item["confidence"] * 0.15,
    )

    summary = {
        "bestSetup": ranked[0],
        "worstSetup": ranked[-1],
        "bestRiskReward": best_risk_reward,
        "highestRisk": highest_risk,
        "strongestCrypto": strongest_crypto,
        "strongestStock": strongest_stock,
        "overallMarketTone": summarize_market_tone(assets),
    }

    return {"ranked": ranked, "summary": summary}


def build_dashboard() -> dict:
    assets = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            (asset_config, executor.submit(build_asset_from_yahoo, asset_config))
            for asset_config in ASSETS
        ]

        for asset_config, future in futures:
            try:
                assets.append(future.result())
            except Exception as error:
                assets.append(fallback_asset(asset_config, error))

    assets.sort(key=lambda item: next(index for index, config in enumerate(ASSETS) if config["ticker"] == item["ticker"]))
    recommendations = build_recommendations(assets)

    return {
        "generatedAt": now_iso(),
        "assets": assets,
        "recommendations": recommendations,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/dashboard":
            self.serve_dashboard()
            return

        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()

    def serve_dashboard(self):
        global cache_payload
        global cache_time

        with cache_lock:
            if cache_payload and (time.time() - cache_time) < CACHE_TTL_SECONDS:
                payload = cache_payload
            else:
                try:
                    payload = build_dashboard()
                    cache_payload = payload
                    cache_time = time.time()
                except Exception as error:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "error": "Could not build dashboard data.",
                                "details": str(error),
                            }
                        ).encode("utf-8")
                    )
                    return

        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Serving market dashboard at http://{HOST}:{PORT}")
    server.serve_forever()
