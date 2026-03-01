"""IPO Sentiment Tracker - main entry point.

Usage:
    python main.py producer   # Run producer once (fetch + push to Kafka)
    python main.py consumer   # Run consumer loop (blocks forever)
    python main.py scheduler  # Run producer on a 30-minute schedule
"""

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TICKERS_PATH = Path(__file__).parent / "config" / "tickers.json"


def load_tickers() -> list[dict]:
    with open(TICKERS_PATH) as f:
        data = json.load(f)
    return data["tickers"]


def run_producer():
    from producer import newsapi_producer, rss_producer

    tickers = load_tickers()

    newsapi_count = newsapi_producer.fetch_and_produce(tickers)
    rss_count = rss_producer.fetch_and_produce(tickers)
    logger.info("Producer run complete: %d NewsAPI + %d RSS messages", newsapi_count, rss_count)


def run_consumer():
    from consumer.sentiment_consumer import run_consumer as _run_consumer

    tickers = load_tickers()
    _run_consumer(tickers)


def run_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(run_producer, "interval", minutes=30, id="producer_job")
    logger.info("Scheduler started. Producer runs every 30 minutes.")
    run_producer()  # run once immediately
    scheduler.start()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "producer":
        run_producer()
    elif command == "consumer":
        run_consumer()
    elif command == "scheduler":
        run_scheduler()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
