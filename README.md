# IPO Sentiment Tracker

A real-time pipeline that streams IPO-related news, analyzes sentiment using an LLM, and visualizes sentiment trends over time on a PostHog dashboard.

## Architecture

```
tickers.json
     |
     v
+-----------+       +-------+       +--------------------+       +---------+
| NewsAPI   |------>|       |       |                    |       |         |
+-----------+       |       |       |                    |       |         |
| Google    |------>| Kafka |------>| Sentiment Consumer |------>| PostHog |
| News RSS  |       |       |       | (OpenAI GPT-4o)    |       |         |
+-----------+       |       |       |                    |       |         |
| Yahoo     |------>|       |       +--------------------+       +---------+
| Finance   |       +-------+
+-----------+              Dedup via SQLite
| Seeking   |------>|
| Alpha RSS |
+-----------+
  (Producers run every 30 min)       (Consumer runs continuously)
```

**Flow:**

1. Producers fetch IPO-related news for each ticker from NewsAPI, Google News RSS, Yahoo Finance RSS, and Seeking Alpha RSS
2. Articles are deduplicated by URL using a persistent SQLite database and pushed to a Kafka topic (`ipo-news-raw`)
3. The consumer reads each message, calls OpenAI for sentiment analysis (positive/negative/neutral label, numeric score from -1.0 to 1.0, and confidence)
4. Structured events are sent to PostHog for dashboard visualization
5. Failed API calls (OpenAI, PostHog) are retried up to 3 times with exponential backoff

## Prerequisites

- Python 3.10+
- Docker and Docker Compose (for Kafka)
- API keys for NewsAPI, OpenAI, and PostHog

## Setup

### 1. Clone and install dependencies

```bash
cd ipo-sentiment-tracker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Edit `.env` and fill in your API keys:

```
NEWSAPI_KEY=your_newsapi_key
OPENAI_API_KEY=your_openai_key
POSTHOG_API_KEY=your_posthog_project_key
POSTHOG_HOST=https://app.posthog.com
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

### 3. Configure tickers

Edit `config/tickers.json` to add the IPO tickers you want to track:

```json
{
  "tickers": [
    {
      "symbol": "GENB",
      "company_name": "Generate Biomedicines",
      "listing_date": "2026-02-26"
    }
  ]
}
```

### 4. Start Kafka

```bash
docker compose up -d
```

Wait a few seconds for Kafka to initialize.

## Usage

Run the **producer** once (fetches news and pushes to Kafka):

```bash
python main.py producer
```

Run the **consumer** (blocks and processes messages as they arrive):

```bash
python main.py consumer
```

Run the **scheduler** (producer executes every 30 minutes automatically):

```bash
python main.py scheduler
```

In a typical setup, run the consumer in one terminal and the scheduler in another.

## Kafka Message Format

Each message on the `ipo-news-raw` topic:

```json
{
  "ticker": "GENB",
  "title": "Generate Biomedicines prices IPO at $16 per share",
  "source": "newsapi",
  "url": "https://...",
  "published_at": "2026-02-26T08:00:00+00:00",
  "content_snippet": "..."
}
```

## PostHog Event

The consumer sends `ipo_sentiment_captured` events with these properties:

```json
{
  "ticker": "GENB",
  "sentiment": "positive",
  "sentiment_score": 0.7,
  "confidence": 0.85,
  "key_signal": "Strong institutional interest reported ahead of listing",
  "source": "newsapi",
  "published_at": "2026-02-26T08:00:00+00:00",
  "days_to_listing": 3
}
```

## PostHog Dashboard Setup

Create a new dashboard in PostHog and add these insights:

1. **Sentiment trend** -- Line chart of `ipo_sentiment_captured` events over time, Y-axis = average `sentiment_score`, broken down by `ticker`
2. **Sentiment breakdown** -- Bar chart showing count of positive / negative / neutral per ticker
3. **Article volume** -- Line chart of event count per day, broken down by `ticker`

## Project Structure

```
ipo-sentiment-tracker/
├── producer/
│   ├── newsapi_producer.py       # Fetch from NewsAPI, push to Kafka
│   ├── rss_producer.py           # Fetch from Google/Yahoo/Seeking Alpha RSS
│   └── utils.py                  # Persistent dedup (SQLite), cleaning helpers
├── consumer/
│   ├── sentiment_consumer.py     # Consume Kafka, run LLM sentiment, send to PostHog
│   └── prompts.py                # LLM prompt templates
├── config/
│   └── tickers.json              # List of IPO tickers to track
├── data/
│   └── dedup.db                  # SQLite dedup database (auto-created, git-ignored)
├── docker-compose.yml            # Kafka + Zookeeper setup
├── main.py                       # CLI entry point (producer / consumer / scheduler)
├── .env                          # API keys (not committed)
├── requirements.txt
└── README.md
```

## License

MIT
