import json
import logging
import os

from kafka import KafkaProducer
from newsapi import NewsApiClient

from producer.utils import clean_text, is_duplicate, parse_iso_datetime

logger = logging.getLogger(__name__)

TOPIC = "ipo-news-raw"


def create_producer() -> KafkaProducer:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    return KafkaProducer(
        bootstrap_servers=bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def fetch_and_produce(tickers: list[dict]) -> int:
    """Fetch news from NewsAPI for each ticker and push to Kafka.

    Returns the number of messages produced.
    """
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key or api_key == "your_key":
        logger.warning("NEWSAPI_KEY not set, skipping NewsAPI producer")
        return 0

    newsapi = NewsApiClient(api_key=api_key)
    producer = create_producer()
    count = 0

    for ticker_info in tickers:
        symbol = ticker_info["symbol"]
        company = ticker_info.get("company_name", symbol)
        query = f"{symbol} IPO OR {company} IPO"

        try:
            response = newsapi.get_everything(
                q=query,
                language="en",
                sort_by="publishedAt",
                page_size=20,
            )
        except Exception:
            logger.exception("NewsAPI request failed for %s", symbol)
            continue

        articles = response.get("articles", [])
        logger.info("NewsAPI returned %d articles for %s", len(articles), symbol)

        for article in articles:
            url = article.get("url", "")
            if not url or is_duplicate(url):
                continue

            message = {
                "ticker": symbol,
                "title": clean_text(article.get("title")),
                "source": "newsapi",
                "url": url,
                "published_at": parse_iso_datetime(article.get("publishedAt")),
                "content_snippet": clean_text(
                    article.get("description") or article.get("content", "")
                ),
            }
            producer.send(TOPIC, value=message)
            count += 1

    producer.flush()
    producer.close()
    logger.info("NewsAPI producer sent %d messages", count)
    return count
