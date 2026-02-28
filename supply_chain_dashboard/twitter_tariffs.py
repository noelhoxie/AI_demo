"""
Tariff outlook from X (Twitter): recent tweets about tariffs and tariff forecast (next 6 months).
Uses Twitter API v2 recent search when TWITTER_BEARER_TOKEN is set; otherwise returns realistic sample data.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

from config import TWITTER_BEARER_TOKEN

log = logging.getLogger(__name__)

API_BASE = "https://api.twitter.com/2"
REQUEST_TIMEOUT = 10
MAX_RESULTS = 15
# Search: tariff forecast / outlook for next 6 months discussion
QUERY = '(tariff forecast OR tariff outlook OR tariffs 2025 OR tariffs next 6 months) -is:retweet lang:en'

# Realistic sample tweets for when API is not configured or returns no results
MOCK_TWEETS: List[Dict[str, Any]] = [
    {
        "author_name": "Trade Policy Watch",
        "author_username": "TradePolicyWatch",
        "text": "Tariff outlook next 6 months: expect more Section 301 focus on electronics and EV components. China remains in the crosshairs; Southeast Asia could see relief as supply chains diversify.",
        "created_at": (datetime.utcnow() - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 127,
        "reply_count": 23,
    },
    {
        "author_name": "Supply Chain Daily",
        "author_username": "SupplyChainDaily",
        "text": "Analysts are revising tariff forecasts for H2 2025. Key variables: election outcome, US-EU talks, and whether additional 301 exclusions get extended. Plan for 2–3% COGS uplift on affected categories.",
        "created_at": (datetime.utcnow() - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 89,
        "reply_count": 15,
    },
    {
        "author_name": "Peter Chen",
        "author_username": "pchen_trade",
        "text": "Tariff forecast for the next 6 months isn’t just about rates—it’s about which product lines get exclusions. If you’re in industrial machinery or chemicals, watch the Federal Register for new exclusion requests.",
        "created_at": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 204,
        "reply_count": 41,
    },
    {
        "author_name": "Global Trade Alert",
        "author_username": "GlobalTradeAlert",
        "text": "Our 6-month tariff forecast: US likely to keep pressure on China while offering more carve-outs for allies. Mexico/Canada remain in USMCA sweet spot. EU 232/301 truce could extend into 2025.",
        "created_at": (datetime.utcnow() - timedelta(days=1, hours=6)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 312,
        "reply_count": 56,
    },
    {
        "author_name": "Procurement Weekly",
        "author_username": "ProcurementWkly",
        "text": "Heads up: if your company sources steel, aluminum, or solar components, tariff rates could shift again in the next 6 months. DC is weighing new AD/CVD petitions. Lock in contracts or hedge where you can.",
        "created_at": (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 67,
        "reply_count": 12,
    },
    {
        "author_name": "Maria Santos",
        "author_username": "msantos_logistics",
        "text": "Tariff outlook 2025: expect more country-by-country variance. Vietnam and India benefiting from diversification; some EU sectors (autos, ag) still in the spotlight. Plan your landed cost models accordingly.",
        "created_at": (datetime.utcnow() - timedelta(days=2, hours=8)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 143,
        "reply_count": 28,
    },
    {
        "author_name": "Washington Trade",
        "author_username": "WashTrade",
        "text": "Next 6 months will be decisive for tariff policy. Key dates: exclusion renewals, potential new 301 list, and trade agreement reviews. Our forecast: elevated uncertainty through Q2, then clearer direction.",
        "created_at": (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "like_count": 198,
        "reply_count": 34,
    },
]


def _search_recent_tweets() -> Dict[str, Any]:
    if not TWITTER_BEARER_TOKEN:
        return {"configured": False, "data": None, "error": None}
    url = f"{API_BASE}/tweets/search/recent"
    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
    params = {
        "query": QUERY,
        "max_results": min(MAX_RESULTS, 100),
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "name,username",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code == 401:
            return {"configured": True, "data": None, "error": "Invalid or expired token"}
        if r.status_code == 403:
            return {"configured": True, "data": None, "error": "Access denied (check API plan)"}
        r.raise_for_status()
        return {"configured": True, "data": r.json(), "error": None}
    except requests.RequestException as e:
        log.warning("Twitter API request failed: %s", e)
        return {"configured": True, "data": None, "error": str(e)}


def _mock_tweet_list() -> List[Dict[str, Any]]:
    """Return copy of mock tweets with consistent shape (created_at is dynamic)."""
    base = datetime.utcnow()
    out = []
    for i, t in enumerate(MOCK_TWEETS):
        # Slightly stagger mock created_at so they don’t all match one refresh
        t_copy = dict(t)
        if i > 0 and isinstance(t.get("created_at"), str):
            try:
                dt = datetime.strptime(t["created_at"][:19], "%Y-%m-%dT%H:%M:%S")
                t_copy["created_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            except Exception:
                pass
        out.append(t_copy)
    return out


def get_tariff_forecast_from_twitter() -> Dict[str, Any]:
    """
    Fetch recent X (Twitter) discussion about tariff forecast / outlook.
    When API is not configured or returns nothing, returns realistic sample tweets.
    Returns: { "configured": bool, "tweets": [...], "summary": str, "error": str or None, "sample_data": bool }
    """
    out: Dict[str, Any] = {
        "configured": False,
        "tweets": [],
        "summary": None,
        "error": None,
        "sample_data": False,
    }
    result = _search_recent_tweets()
    out["configured"] = result["configured"]

    if result.get("data"):
        data = result["data"]
        includes = data.get("includes") or {}
        users_by_id = {u["id"]: u for u in includes.get("users") or []}
        tweets_raw = data.get("data") or []
        tweets: List[Dict[str, Any]] = []
        for t in tweets_raw:
            author = (users_by_id.get(t.get("author_id") or "") or {})
            tweets.append({
                "id": t.get("id"),
                "text": (t.get("text") or "").strip(),
                "created_at": t.get("created_at"),
                "author_name": author.get("name") or author.get("username") or "Unknown",
                "author_username": author.get("username") or "",
                "like_count": (t.get("public_metrics") or {}).get("like_count", 0),
                "reply_count": (t.get("public_metrics") or {}).get("reply_count", 0),
            })
        if tweets:
            out["tweets"] = tweets
            out["summary"] = f"Recent discussion on X about tariff outlook (next 6 months). {len(tweets)} tweets from the last 7 days."
            return out

    # Not configured: show clear message only (no sample tweets)
    if not result["configured"]:
        out["summary"] = "Twitter is not configured. Set TWITTER_BEARER_TOKEN in your environment to see live tariff discussion from X."
        return out

    # Configured but no live data: use sample tweets and explain
    out["tweets"] = _mock_tweet_list()
    out["sample_data"] = True
    if result.get("error"):
        out["error"] = result["error"]
        out["summary"] = "Could not load live X data. Showing sample tariff outlook discussion."
    else:
        out["summary"] = "No recent tweets found. Showing sample tariff outlook discussion."
    return out
