import json
import logging
import os
from urllib.parse import quote_plus

import feedparser
from kafka import KafkaProducer

from producer.utils import clean_text, is_duplicate, parse_iso_datetime

logger = logging.getLogger(__name__)

TOPIC = "ipo-news-raw"

RSS_FEEDS = {
    "google_news": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    "yahoo_finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
    "seeking_alpha": "https://seekingalpha.com/api/sa/combined/{symbol}.xml",
}


def create_producer() -> KafkaProducer:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    return KafkaProducer(
        bootstrap_servers=bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def _fetch_google_news(symbol: str, company: str) -> list[tuple[str, dict]]:
    """Fetch from Google News RSS. Returns list of (source_name, entry) tuples."""
    query = quote_plus(f"{symbol} IPO {company}")
    feed_url = RSS_FEEDS["google_news"].format(query=query)
    try:
        feed = feedparser.parse(feed_url)
        entries = feed.get("entries", [])
        logger.info("Google News RSS returned %d entries for %s", len(entries), symbol)
        return [("google_news_rss", e) for e in entries]
    except Exception:
        logger.exception("Google News RSS fetch failed for %s", symbol)
        return []


def _fetch_yahoo_finance(symbol: str) -> list[tuple[str, dict]]:
    """Fetch from Yahoo Finance RSS."""
    feed_url = RSS_FEEDS["yahoo_finance"].format(symbol=symbol)
    try:
        feed = feedparser.parse(feed_url)
        entries = feed.get("entries", [])
        logger.info("Yahoo Finance RSS returned %d entries for %s", len(entries), symbol)
        return [("yahoo_finance_rss", e) for e in entries]
    except Exception:
        logger.exception("Yahoo Finance RSS fetch failed for %s", symbol)
        return []


def _fetch_seeking_alpha(symbol: str) -> list[tuple[str, dict]]:
    """Fetch from Seeking Alpha RSS."""
    feed_url = RSS_FEEDS["seeking_alpha"].format(symbol=symbol)
    try:
        feed = feedparser.parse(feed_url)
        entries = feed.get("entries", [])
        logger.info("Seeking Alpha RSS returned %d entries for %s", len(entries), symbol)
        return [("seeking_alpha_rss", e) for e in entries]
    except Exception:
        logger.exception("Seeking Alpha RSS fetch failed for %s", symbol)
        return []


def fetch_and_produce(tickers: list[dict]) -> int:
    """Fetch news from multiple RSS sources for each ticker and push to Kafka.

    Returns the number of messages produced.
    """
    producer = create_producer()
    count = 0

    for ticker_info in tickers:
        symbol = ticker_info["symbol"]
        company = ticker_info.get("company_name", symbol)

        all_entries: list[tuple[str, dict]] = []
        all_entries.extend(_fetch_google_news(symbol, company))
        all_entries.extend(_fetch_yahoo_finance(symbol))
        all_entries.extend(_fetch_seeking_alpha(symbol))

        for source_name, entry in all_entries:
            url = entry.get("link", "")
            if not url or is_duplicate(url):
                continue

            published = entry.get("published", "")
            message = {
                "ticker": symbol,
                "title": clean_text(entry.get("title")),
                "source": source_name,
                "url": url,
                "published_at": parse_iso_datetime(published),
                "content_snippet": clean_text(entry.get("summary", "")),
            }
            producer.send(TOPIC, value=message)
            count += 1

    producer.flush()
    producer.close()
    logger.info("RSS producer sent %d messages total", count)
    return count
