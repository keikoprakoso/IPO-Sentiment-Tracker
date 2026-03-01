SENTIMENT_PROMPT = """You are a financial analyst. Given the following news snippet about an upcoming IPO, \
analyze the sentiment from an investor's perspective.

Ticker: {ticker}
Headline: {title}
Snippet: {content_snippet}

Respond ONLY in this JSON format, no other text:
{{
  "sentiment": "positive" | "negative" | "neutral",
  "sentiment_score": float between -1.0 (very negative) and 1.0 (very positive),
  "confidence": float between 0 and 1,
  "key_signal": "one sentence explaining the main signal"
}}"""
