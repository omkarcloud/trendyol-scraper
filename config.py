"""Configuration for the Trendyol Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT            port the API listens on (default 8000)
    TRENDYOL_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                    (default: none — direct). Trendyol answered every endpoint
                    from a plain cloud server IP with no proxy, so you very
                    likely don't need this. Set it only if you start seeing
                    failures at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

TRENDYOL_PROXY = os.environ.get("TRENDYOL_PROXY") or None


def trendyol_proxy():
    """The proxy for a new HTTP session (None = direct)."""
    return os.environ.get("TRENDYOL_PROXY") or None
