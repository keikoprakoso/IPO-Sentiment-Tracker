import json
import logging
import os
import time
from datetime import date

import openai
from kafka import KafkaConsumer
from posthog import Posthog

from consumer.prompts import SENTIMENT_PROMPT

logger = logging.getLogger(__name__)

TOPIC = "ipo-news-raw"
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each attempt


def _load_listing_dates(tickers: list[dict]) -> dict[str, date]:
    """Build a symbol -> listing_date mapping."""
    mapping: dict[str, date] = {}
    for t in tickers:
        try:
            mapping[t["symbol"]] = date.fromisoformat(t["listing_date"])
        except (KeyError, ValueError):
            continue
    return mapping


def _days_to_listing(ticker: str, listing_dates: dict[str, date]) -> int | None:
    """Calculate days from today to the listing date for a ticker."""
    listing = listing_dates.get(ticker)
    if listing is None:
        return None
    return (listing - date.today()).days


def _create_openai_client() -> openai.OpenAI | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_key":
        logger.warning("OPENAI_API_KEY not set, skipping sentiment analysis")
        return None
    return openai.OpenAI(api_key=api_key)


def _create_posthog_client() -> Posthog | None:
    api_key = os.getenv("POSTHOG_API_KEY")
    host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    if not api_key or api_key == "your_key":
        logger.warning("POSTHOG_API_KEY not set, skipping PostHog events")
        return None
    return Posthog(api_key, host=host)


def _retry(fn, description: str):
    """Call fn() with exponential backoff. Returns result or None on failure."""
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception:
            wait = RETRY_BACKOFF * (2 ** attempt)
            logger.warning(
                "%s failed (attempt %d/%d), retrying in %ds...",
                description, attempt + 1, MAX_RETRIES, wait,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
            else:
                logger.exception("%s failed after %d attempts", description, MAX_RETRIES)
    return None


def _analyze_sentiment(oai_client: openai.OpenAI, article: dict) -> dict | None:
    """Call OpenAI to get sentiment analysis for an article, with retry."""
    prompt = SENTIMENT_PROMPT.format(
        ticker=article.get("ticker", ""),
        title=article.get("title", ""),
        content_snippet=article.get("content_snippet", ""),
    )

    def call():
        response = oai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200,
        )
        content = response.choices[0].message.content.strip()
        return json.loads(content)

    result = _retry(call, f"Sentiment analysis for '{article.get('title', '')[:50]}'")
    return result


def _send_to_posthog(
    ph_client: Posthog, article: dict, sentiment: dict, days_to_listing: int | None
):
    """Send a structured event to PostHog, with retry."""
    properties = {
        "ticker": article.get("ticker"),
        "sentiment": sentiment.get("sentiment"),
        "sentiment_score": sentiment.get("sentiment_score"),
        "confidence": sentiment.get("confidence"),
        "key_signal": sentiment.get("key_signal"),
        "source": article.get("source"),
        "published_at": article.get("published_at"),
        "url": article.get("url"),
        "title": article.get("title"),
    }
    if days_to_listing is not None:
        properties["days_to_listing"] = days_to_listing

    def call():
        ph_client.capture(
            distinct_id=f"ipo-tracker-{article.get('ticker', 'unknown')}",
            event="ipo_sentiment_captured",
            properties=properties,
        )

    _retry(call, f"PostHog capture for '{article.get('ticker')}'")
    logger.info(
        "Sent to PostHog: ticker=%s sentiment=%s score=%s confidence=%s",
        article.get("ticker"),
        sentiment.get("sentiment"),
        sentiment.get("sentiment_score"),
        sentiment.get("confidence"),
    )


def run_consumer(tickers: list[dict]):
    """Main consumer loop. Blocks indefinitely, consuming messages from Kafka."""
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    listing_dates = _load_listing_dates(tickers)

    oai_client = _create_openai_client()
    ph_client = _create_posthog_client()

    if oai_client is None or ph_client is None:
        logger.error("Missing API clients, cannot start consumer")
        return

    logger.info("Starting consumer, connecting to %s", bootstrap)

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=bootstrap,
        auto_offset_reset="earliest",
        group_id="ipo-sentiment-group",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    logger.info("Consumer connected, waiting for messages...")

    for message in consumer:
        article = message.value
        logger.info("Received article: %s [%s]", article.get("title", "")[:60], article.get("ticker"))

        sentiment = _analyze_sentiment(oai_client, article)
        if sentiment is None:
            continue

        dtl = _days_to_listing(article.get("ticker", ""), listing_dates)
        _send_to_posthog(ph_client, article, sentiment, dtl)
