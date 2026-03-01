import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "dedup.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen_urls (url_hash TEXT PRIMARY KEY, first_seen TEXT)"
    )
    conn.commit()
    return conn


def normalize_url(url: str) -> str:
    """Strip tracking params and fragments for consistent dedup."""
    url = url.split("?")[0].split("#")[0]
    return url.rstrip("/")


def is_duplicate(url: str) -> bool:
    """Return True if this URL has already been seen (persisted in SQLite)."""
    normalized = normalize_url(url)
    url_hash = hashlib.sha256(normalized.encode()).hexdigest()

    conn = _get_db()
    row = conn.execute("SELECT 1 FROM seen_urls WHERE url_hash = ?", (url_hash,)).fetchone()
    if row:
        conn.close()
        return True

    conn.execute(
        "INSERT INTO seen_urls (url_hash, first_seen) VALUES (?, ?)",
        (url_hash, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return False


def clean_text(text: str | None) -> str:
    """Remove excessive whitespace and HTML remnants from text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_iso_datetime(dt_str: str | None) -> str:
    """Best-effort parse to ISO 8601 string. Returns empty string on failure."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, TypeError):
        return dt_str
